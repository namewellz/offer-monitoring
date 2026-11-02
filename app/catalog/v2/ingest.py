"""Dual-write ingestion for the v2 catalog model.

Writes runs, source products, versions, listings and price periods without
touching the legacy tables. The legacy ``persist_*`` functions call
``ingest_catalog_v2`` inside their own transaction, so a single collection
updates both models atomically (section 20.3 of the architecture document).

The price-period algorithm follows section 9.3: an unchanged state only bumps
``confirmation_count``; a changed state closes the open period and opens a new
one; a missing period creates version 1. Unknown/withheld prices never close the
last known period.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.catalog.v2.hashing import (
    digest,
    identity_input_state,
    price_state,
    source_product_state,
)
from app.catalog.v2.read import shelf_previous_cents
from app.catalog.v2.registry import (
    CATALOG_SOURCES,
    COLLECTOR_VERSION,
    source_config_for,
    target_defaults_for,
)
from app.db.models import Retailer, Store
from app.db.models_v2 import (
    CatalogSource,
    CollectionRun,
    CollectionRunError,
    CollectionTarget,
    PricePeriod,
    SourceProduct,
    SourceProductVersion,
    StoreListing,
)


def _observed_at(catalog: dict[str, Any]) -> datetime:
    value = catalog["collected_at"]
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(value)


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _bounded(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:maximum] if text else None


def _effective_price(raw: dict[str, Any]) -> Any:
    value = raw.get("sales_price")
    if value is None or value == "":
        return None
    try:
        if float(value) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return value


def _availability(raw: dict[str, Any]) -> str:
    available = raw.get("available")
    if available is True:
        return "AVAILABLE"
    if available is False:
        return "OUT_OF_STOCK"
    return "UNKNOWN"


def _price_status(raw: dict[str, Any]) -> str:
    if _effective_price(raw) is not None:
        return "KNOWN"
    if raw.get("available") is False:
        return "UNAVAILABLE"
    return "UNKNOWN"


def ensure_source(
    db: Session,
    retailer: Retailer,
    provider_type: str,
    base_url: str,
) -> CatalogSource:
    config = source_config_for(retailer.slug)
    source = db.scalar(
        select(CatalogSource).where(
            CatalogSource.retailer_id == retailer.id,
            CatalogSource.code == config.code,
        )
    )
    if source is None:
        source = CatalogSource(
            retailer_id=retailer.id,
            code=config.code,
            provider_type=provider_type or config.provider_type,
            base_url=base_url or "",
            active=True,
        )
        db.add(source)
        db.flush()
    else:
        source.provider_type = provider_type or source.provider_type
        source.base_url = base_url or source.base_url
    return source


def ensure_store(
    db: Session,
    retailer: Retailer,
    store: Store | None,
) -> Store:
    if store is not None:
        return store
    virtual = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.city == "Nacional",
        )
    )
    if virtual is None:
        virtual = Store(
            retailer_id=retailer.id,
            name=f"{retailer.name} — Nacional",
            city="Nacional",
            state="BR",
        )
        db.add(virtual)
        db.flush()
    return virtual


def ensure_target(
    db: Session,
    source: CatalogSource,
    store: Store,
    retailer_slug: str,
    store_payload: dict[str, Any] | None,
) -> CollectionTarget:
    defaults = target_defaults_for(retailer_slug)
    payload = store_payload or {}
    target_key = f"{retailer_slug}-{_slug(store.name or store.city)}"
    target = db.scalar(
        select(CollectionTarget).where(
            CollectionTarget.source_id == source.id,
            CollectionTarget.target_key == target_key,
        )
    )
    if target is None:
        target = CollectionTarget(
            source_id=source.id,
            store_id=store.id,
            target_key=target_key,
            external_store_id=payload.get("store_id") or defaults.external_store_id,
            external_store_code=payload.get("store_code") or defaults.external_store_code,
            seller_id=payload.get("seller") or defaults.seller_id,
            sales_channel=payload.get("sales_channel") or defaults.sales_channel,
            reference_postal_code=payload.get("postal_code")
            or defaults.reference_postal_code,
            public_config={key: value for key, value in payload.items() if key not in {
                "name", "city", "state", "postal_code", "store_id", "store_code",
                "seller", "sales_channel",
            }},
            active=True,
        )
        db.add(target)
        db.flush()
    else:
        target.external_store_id = (
            payload.get("store_id") or target.external_store_id
        )
        target.external_store_code = (
            payload.get("store_code") or target.external_store_code
        )
        target.seller_id = payload.get("seller") or target.seller_id
        target.sales_channel = payload.get("sales_channel") or target.sales_channel
        target.reference_postal_code = (
            payload.get("postal_code") or target.reference_postal_code
        )
    return target


def create_run(
    db: Session,
    target: CollectionTarget,
    observed_at: datetime,
    trigger_type: str,
) -> CollectionRun:
    run = CollectionRun(
        target_id=target.id,
        ingestion_key=uuid4(),
        status="RUNNING",
        trigger_type=trigger_type,
        started_at=datetime.now(UTC),
        observed_at=observed_at,
        collector_version=COLLECTOR_VERSION,
    )
    db.add(run)
    db.flush()
    return run


def _upsert_source_product(
    db: Session,
    run: CollectionRun,
    source: CatalogSource,
    raw: dict[str, Any],
    observed_at: datetime,
) -> tuple[SourceProduct, SourceProductVersion, bool, bool]:
    external_id = str(raw["id"])
    product = db.scalar(
        select(SourceProduct).where(
            SourceProduct.source_id == source.id,
            SourceProduct.external_id == external_id,
        )
    )
    is_new_product = product is None
    if product is None:
        product = SourceProduct(
            source_id=source.id,
            external_id=external_id,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            active=True,
        )
        db.add(product)
        db.flush()

    state = source_product_state(
        name=raw.get("name"),
        brand=raw.get("brand"),
        gtin=raw.get("ean"),
        categories=raw.get("categories"),
        measure=raw.get("measure"),
        product_url=raw.get("product_url"),
    )
    raw_hash = digest(state)
    identity_hash = digest(identity_input_state(state))

    open_version = db.scalar(
        select(SourceProductVersion)
        .where(
            SourceProductVersion.source_product_id == product.id,
            SourceProductVersion.valid_until.is_(None),
        )
        .with_for_update()
    )
    is_new_version = False
    if open_version is not None and open_version.raw_hash == raw_hash:
        version = open_version
    else:
        if open_version is not None:
            open_version.valid_until = observed_at
        next_version = (open_version.version if open_version is not None else 0) + 1
        version = SourceProductVersion(
            source_product_id=product.id,
            version=next_version,
            raw_name=str(raw.get("name") or "").strip(),
            raw_brand=_bounded(raw.get("brand"), 160),
            raw_gtin=_bounded(raw.get("ean"), 32),
            raw_categories=[str(c) for c in (raw.get("categories") or [])],
            department=canonical_department(
                [str(c) for c in (raw.get("categories") or [])],
                str(raw.get("name") or ""),
            ),
            raw_measure=_bounded(raw.get("measure"), 50),
            raw_product_url=raw.get("product_url"),
            raw_image_url=raw.get("image_url"),
            raw_hash=raw_hash,
            identity_input_hash=identity_hash,
            valid_from=observed_at,
            first_run_id=run.id,
        )
        db.add(version)
        db.flush()
        product.current_version_id = version.id
        is_new_version = True

    product.internal_code = _bounded(raw.get("internal_code"), 120)
    product.current_product_url = raw.get("product_url")
    product.current_image_url = raw.get("image_url")
    product.last_seen_at = observed_at
    return product, version, is_new_product, is_new_version


def _is_offer(
    regular_cents: int | None,
    effective_cents: int | None,
    best_conditional: int | None,
    terms: list[dict[str, Any]],
) -> bool:
    if (
        regular_cents is not None
        and effective_cents is not None
        and effective_cents < regular_cents
    ):
        return True
    if best_conditional is not None:
        return True
    return bool(terms)


def _offer_kind(
    regular_cents: int | None,
    effective_cents: int | None,
    best_conditional: int | None,
    terms: list[dict[str, Any]],
) -> str | None:
    """Classifica a oferta na escrita, para o filtro/ordenação não derivar na leitura."""
    tiers = [term for term in terms if term.get("kind") == "tier"]
    tags = [term for term in terms if term.get("kind") == "tag"]
    if best_conditional is not None or any(
        term.get("condition") == "club" for term in tiers
    ):
        return "club"
    if any(term.get("condition") == "wholesale" for term in tiers):
        return "wholesale"
    if any(term.get("condition") == "app" for term in tiers):
        return "app"
    if any(
        int(term.get("minimum_quantity") or 1) > 1
        and term.get("condition", "quantity") == "quantity"
        for term in tiers
    ):
        return "quantity"
    if tags:
        return "promotion"
    if (
        regular_cents is not None
        and effective_cents is not None
        and effective_cents < regular_cents
    ):
        return "price_drop"
    return None


def _sync_listing_snapshot(
    listing: StoreListing,
    period: PricePeriod,
    previous: PricePeriod | None,
    changed: bool,
) -> None:
    """Escreve no read model o estado que a tela vai ler (sem derivar depois)."""
    terms = [term for term in (period.price_terms or []) if isinstance(term, dict)]
    listing.price_terms = terms
    listing.regular_price_cents = period.regular_price_cents
    listing.effective_price_cents = period.effective_price_cents
    listing.best_conditional_cents = period.best_conditional_price_cents
    listing.price_basis_unit = period.price_basis_unit
    listing.last_confirmed_at = period.last_confirmed_at
    listing.is_offer = _is_offer(
        period.regular_price_cents,
        period.effective_price_cents,
        period.best_conditional_price_cents,
        terms,
    )
    listing.offer_kind = _offer_kind(
        period.regular_price_cents,
        period.effective_price_cents,
        period.best_conditional_price_cents,
        terms,
    )
    if not changed:
        return
    baseline = shelf_previous_cents(
        current_cents=period.effective_price_cents,
        regular_cents=period.regular_price_cents,
        best_conditional=period.best_conditional_price_cents,
        terms=terms,
        previous_effective=previous.effective_price_cents if previous else None,
        previous_regular=previous.regular_price_cents if previous else None,
    )
    listing.previous_cents = baseline
    if baseline is not None and baseline > 0:
        amount = period.effective_price_cents - baseline
        listing.change_amount_cents = amount
        listing.change_percent = (
            Decimal(amount) * 100 / Decimal(baseline)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        listing.change_amount_cents = None
        listing.change_percent = None


def _apply_price_period(
    db: Session,
    run: CollectionRun,
    listing: StoreListing,
    raw: dict[str, Any],
    observed_at: datetime,
) -> tuple[PricePeriod | None, PricePeriod | None, bool]:
    """Apply one incoming price observation.

    Returns ``(open_period, previous_period, changed)``:

    - ``(None, None, False)`` — delayed collection, ignored (section 9.6);
    - ``(open_period, None, False)`` — same state, only re-confirmed;
    - ``(new_period, previous_period, True)`` — a period was created.
    """
    state = price_state(
        regular_price=raw.get("regular_price"),
        effective_price=raw.get("sales_price"),
        tier_prices=raw.get("tier_prices"),
        offer_tags=raw.get("offer_tags"),
        measure=raw.get("measure"),
    )
    state_hash = digest(state)
    regular_cents = state["regular_price_cents"]
    if regular_cents is not None and regular_cents <= 0:
        regular_cents = None
    price_terms = [
        {
            "kind": "tier",
            "minimum_quantity": tier["minimum_quantity"],
            "cents": tier["cents"],
            "condition": tier["condition"],
        }
        for tier in state["tier_prices"]
    ]
    price_terms += [{"kind": "tag", "value": tag} for tag in state["offer_tags"]]
    open_period = db.scalar(
        select(PricePeriod)
        .where(
            PricePeriod.store_listing_id == listing.id,
            PricePeriod.ended_at.is_(None),
        )
        .with_for_update()
    )

    if open_period is None:
        period = PricePeriod(
            store_listing_id=listing.id,
            version=1,
            started_at=observed_at,
            last_confirmed_at=observed_at,
            first_run_id=run.id,
            last_run_id=run.id,
            confirmation_count=1,
            currency=state["currency"],
            regular_price_cents=regular_cents,
            effective_price_cents=state["effective_price_cents"],
            best_conditional_price_cents=state["best_conditional_price_cents"],
            price_basis_unit=state["price_basis_unit"],
            price_terms=price_terms,
            state_hash=state_hash,
        )
        db.add(period)
        return period, None, True

    # A delayed collection must never replace the current state (section 9.6).
    if observed_at < open_period.started_at:
        return None, None, False

    if open_period.state_hash == state_hash:
        open_period.confirmation_count += 1
        open_period.last_confirmed_at = max(observed_at, open_period.last_confirmed_at)
        open_period.last_run_id = run.id
        return open_period, None, False

    open_period.ended_at = observed_at
    period = PricePeriod(
        store_listing_id=listing.id,
        version=open_period.version + 1,
        started_at=observed_at,
        last_confirmed_at=observed_at,
        first_run_id=run.id,
        last_run_id=run.id,
        confirmation_count=1,
        currency=state["currency"],
        regular_price_cents=regular_cents,
        effective_price_cents=state["effective_price_cents"],
        best_conditional_price_cents=state["best_conditional_price_cents"],
        price_basis_unit=state["price_basis_unit"],
        price_terms=price_terms,
        state_hash=state_hash,
    )
    db.add(period)
    return period, open_period, True


def record_errors(db: Session, run: CollectionRun, catalog: dict[str, Any]) -> None:
    for sequence, issue in enumerate(catalog.get("collection_errors") or [], start=1):
        if not isinstance(issue, dict):
            continue
        message = str(issue.get("error") or "unknown")
        error_class, _, detail = message.partition(": ")
        db.add(
            CollectionRunError(
                run_id=run.id,
                sequence=sequence,
                scope_type="page",
                scope_key=str(issue.get("scope") or "unknown")[:255],
                error_class=error_class[:255],
                message=detail or error_class,
            )
        )


def finish_run(
    db: Session,
    run: CollectionRun,
    catalog: dict[str, Any],
    *,
    items_seen: int,
    items_priced: int,
    items_new: int,
    items_changed: int,
    items_unchanged: int,
    periods_created: int,
) -> None:
    errors = catalog.get("collection_errors") or []
    collection_status = catalog.get("collection_status", "SUCCESS")
    run.status = "SUCCESS" if not errors and collection_status == "SUCCESS" else "PARTIAL_SUCCESS"
    run.is_complete = not errors
    run.finished_at = datetime.now(UTC)
    run.items_seen = items_seen
    run.items_priced = items_priced
    run.items_new = items_new
    run.items_changed = items_changed
    run.items_unchanged = items_unchanged
    run.price_periods_created = periods_created
    run.error_count = len(errors)


def ingest_catalog_v2(
    db: Session,
    catalog: dict[str, Any],
    *,
    retailer: Retailer,
    store: Store | None,
    trigger_type: str = "scheduled",
) -> CollectionRun | None:
    """Dual-write one collected catalog into the v2 model."""
    retailer_slug = retailer.slug
    if retailer_slug not in CATALOG_SOURCES:
        return None

    observed_at = _observed_at(catalog)
    source = ensure_source(db, retailer, CATALOG_SOURCES[retailer_slug].provider_type, catalog["source"])
    target_store = ensure_store(db, retailer, store)
    target = ensure_target(db, source, target_store, retailer_slug, catalog.get("store"))
    run = create_run(db, target, observed_at, trigger_type)
    record_errors(db, run, catalog)

    products = catalog.get("products") or []
    items_seen = len(products)
    items_priced = 0
    items_new = 0
    items_changed = 0
    items_unchanged = 0
    periods_created = 0

    for raw in products:
        product, version, is_new_product, is_new_version = _upsert_source_product(
            db, run, source, raw, observed_at
        )
        listing = db.scalar(
            select(StoreListing).where(
                StoreListing.target_id == target.id,
                StoreListing.source_product_id == product.id,
            )
        )
        if listing is None:
            listing = StoreListing(
                target_id=target.id,
                source_product_id=product.id,
                active=True,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            db.add(listing)
            db.flush()

        listing.availability = _availability(raw)
        listing.stock_current = raw.get("stock")
        listing.price_status = _price_status(raw)
        listing.last_seen_at = observed_at
        listing.last_seen_run_id = run.id

        # Read model: produto + loja/rede copiados aqui para a tela nunca precisar
        # de join. O departamento vem da versão (calculado na criação da versão).
        listing.department = version.department or canonical_department(
            version.raw_categories, version.raw_name
        )
        listing.product_external_id = product.external_id
        listing.product_name = version.raw_name
        listing.product_brand = version.raw_brand
        listing.product_gtin = version.raw_gtin
        listing.product_categories = version.raw_categories
        listing.retailer_name = retailer.name
        listing.retailer_slug = retailer.slug
        listing.store_name = target_store.display_name or target_store.name
        listing.store_region_bucket = target_store.region_bucket
        listing.store_city = target_store.city
        listing.store_neighborhood = target_store.neighborhood
        listing.store_type = target_store.store_type

        if is_new_product:
            items_new += 1
        elif is_new_version:
            items_changed += 1
        else:
            items_unchanged += 1

        if listing.price_status == "KNOWN":
            items_priced += 1
            period, previous, changed = _apply_price_period(
                db, run, listing, raw, observed_at
            )
            if period is not None:
                _sync_listing_snapshot(listing, period, previous, changed)
            if changed:
                periods_created += 1

    finish_run(
        db,
        run,
        catalog,
        items_seen=items_seen,
        items_priced=items_priced,
        items_new=items_new,
        items_changed=items_changed,
        items_unchanged=items_unchanged,
        periods_created=periods_created,
    )
    return run


def latest_open_period_for(listing_id: int, db: Session) -> PricePeriod | None:
    return db.scalar(
        select(PricePeriod).where(
            PricePeriod.store_listing_id == listing_id,
            PricePeriod.ended_at.is_(None),
        )
    )


def listing_price_history(db: Session, listing_id: int) -> list[PricePeriod]:
    return list(
        db.scalars(
            select(PricePeriod)
            .where(PricePeriod.store_listing_id == listing_id)
            .order_by(PricePeriod.started_at)
        ).all()
    )
