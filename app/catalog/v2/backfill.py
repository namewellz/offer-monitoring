"""Backfill the v2 model from the legacy catalog tables.

One-time migration utility (section 20.2 of the architecture document). It is
idempotent: sources, targets, source products, versions and listings are
upserted by natural keys, and price periods are rebuilt from scratch for every
listing under a synthetic ``BACKFILL`` run.

The legacy observation table may hold millions of rows, so the transform
streams observations ordered by (product, store, observed_at, id) and collapses
consecutive identical states into islands using the algorithm from section 20.2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import groupby
from uuid import uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.catalog.v2.hashing import cents, digest, price_state
from app.catalog.v2.ingest import ensure_source, ensure_store, ensure_target
from app.catalog.v2.registry import CATALOG_SOURCES
from app.db.models import CatalogProduct, Retailer, Store
from app.db.models_v2 import (
    CatalogSource,
    CollectionRun,
    CollectionTarget,
    PricePeriod,
    SourceProduct,
    SourceProductVersion,
    StoreListing,
)

BACKFILL_COLLECTOR_VERSION = "backfill-legacy-v1"


def _backfill_run(db: Session, target: CollectionTarget) -> CollectionRun:
    run = CollectionRun(
        target_id=target.id,
        ingestion_key=uuid4(),
        status="BACKFILL",
        trigger_type="backfill",
        observed_at=datetime.now(UTC),
        collector_version=BACKFILL_COLLECTOR_VERSION,
        is_complete=True,
    )
    db.add(run)
    db.flush()
    return run


def _ensure_infrastructure(
    db: Session,
) -> tuple[
    dict[str, CatalogSource],
    dict[int, CollectionTarget],
    dict[int, CollectionRun],
]:
    sources: dict[str, CatalogSource] = {}
    targets: dict[int, CollectionTarget] = {}
    runs: dict[int, CollectionRun] = {}
    for slug, config in CATALOG_SOURCES.items():
        retailer = db.scalar(select(Retailer).where(Retailer.slug == slug))
        if retailer is None:
            continue
        source = ensure_source(db, retailer, config.provider_type, "")
        sources[str(retailer.id)] = source
        stores = db.scalars(select(Store).where(Store.retailer_id == retailer.id)).all()
        if not stores:
            stores = [ensure_store(db, retailer, None)]
        for store in stores:
            target = ensure_target(db, source, store, slug, None)
            targets[target.id] = target
            runs[target.id] = _backfill_run(db, target)
    db.flush()
    return sources, targets, runs


def _backfill_products(
    db: Session,
    sources: dict[str, CatalogSource],
    runs: dict[int, CollectionRun],
    targets_by_source: dict[int, list[CollectionTarget]],
) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for source in sources.values():
        fallback_run_id = runs[targets_by_source[source.id][0].id].id
        existing = {
            external_id: product_id
            for external_id, product_id in db.execute(
                select(SourceProduct.external_id, SourceProduct.id).where(
                    SourceProduct.source_id == source.id
                )
            )
        }
        products = db.scalars(
            select(CatalogProduct)
            .where(CatalogProduct.retailer_id == source.retailer_id)
            .order_by(CatalogProduct.id)
        ).yield_per(1000)
        for legacy in products:
            product_id = existing.get(legacy.external_id)
            if product_id is not None:
                mapping[str(legacy.id)] = product_id
                continue
            product = SourceProduct(
                source_id=source.id,
                external_id=legacy.external_id,
                internal_code=legacy.internal_code,
                first_seen_at=legacy.first_seen_at,
                last_seen_at=legacy.last_seen_at,
                active=True,
            )
            db.add(product)
            db.flush()
            version = SourceProductVersion(
                source_product_id=product.id,
                version=1,
                raw_name=legacy.name,
                raw_brand=legacy.brand,
                raw_gtin=legacy.ean,
                raw_categories=legacy.categories or [],
                raw_measure=legacy.measure,
                raw_product_url=legacy.product_url,
                raw_image_url=legacy.image_url,
                raw_hash=digest(
                    {
                        "name": legacy.name,
                        "brand": legacy.brand,
                        "gtin": legacy.ean,
                        "categories": legacy.categories or [],
                        "measure": legacy.measure,
                        "product_url": legacy.product_url,
                    }
                ),
                identity_input_hash=digest(
                    {
                        "name": legacy.name,
                        "brand": legacy.brand,
                        "gtin": legacy.ean,
                        "categories": legacy.categories or [],
                        "measure": legacy.measure,
                    }
                ),
                valid_from=legacy.first_seen_at,
                first_run_id=fallback_run_id,
            )
            db.add(version)
            db.flush()
            product.current_version_id = version.id
            product.current_product_url = legacy.product_url
            product.current_image_url = legacy.image_url
            existing[legacy.external_id] = product.id
            mapping[str(legacy.id)] = product.id
    db.flush()
    return mapping


def _build_listings(
    db: Session,
    sources: dict[str, CatalogSource],
    runs: dict[int, CollectionRun],
    product_mapping: dict[str, int],
) -> tuple[dict[tuple[str, str | None], int], dict[int, int]]:
    listing_map: dict[tuple[str, str | None], int] = {}
    listing_run: dict[int, int] = {}

    target_by_store: dict[tuple[int, str | None], CollectionTarget] = {}
    for target in db.scalars(select(CollectionTarget)).all():
        target_by_store[(target.source_id, str(target.store_id))] = target

    listing_by_pair: dict[tuple[int, int], int] = {}
    for listing in db.scalars(select(StoreListing)).all():
        listing_by_pair[(listing.target_id, listing.source_product_id)] = listing.id

    rows = db.execute(
        text(
            """
            SELECT p.retailer_id, p.id AS product_id, o.store_id
            FROM catalog_price_observations o
            JOIN catalog_products p ON p.id = o.product_id
            GROUP BY p.retailer_id, p.id, o.store_id
            ORDER BY 1, 2, 3
            """
        )
    )
    for retailer_id, product_id, store_id in rows:
        source = sources.get(str(retailer_id))
        if source is None:
            continue
        retailer = db.get(Retailer, source.retailer_id)
        store = db.get(Store, store_id) if store_id else None
        store = ensure_store(db, retailer, store)
        target = target_by_store.get((source.id, str(store.id)))
        if target is None:
            target = ensure_target(db, source, store, retailer.slug, None)
            target_by_store[(source.id, str(store.id))] = target
        run = runs.setdefault(target.id, _backfill_run(db, target))

        product_id_v2 = product_mapping[str(product_id)]
        listing_id = listing_by_pair.get((target.id, product_id_v2))
        if listing_id is None:
            listing = StoreListing(
                target_id=target.id,
                source_product_id=product_id_v2,
                active=True,
                first_seen_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
            )
            db.add(listing)
            db.flush()
            listing_id = listing.id
            listing_by_pair[(target.id, product_id_v2)] = listing_id
        key = (str(product_id), str(store_id) if store_id else None)
        listing_map[key] = listing_id
        listing_run[listing_id] = run.id
    db.flush()
    return listing_map, listing_run


def _rebuild_periods(
    db: Session,
    listing_map: dict[tuple[str, str | None], int],
    listing_run: dict[int, int],
) -> int:
    rows = db.execute(
        text(
            """
            SELECT p.id AS product_id, p.measure, o.store_id, o.observed_at,
                   o.regular_price, o.sales_price, o.offer_tags, o.tier_prices
            FROM catalog_price_observations o
            JOIN catalog_products p ON p.id = o.product_id
            ORDER BY p.id, o.store_id NULLS LAST, o.observed_at, o.id
            """
        )
    )
    current_listing: int | None = None
    current_hash: bytes | None = None
    current_start: datetime | None = None
    current_last: datetime | None = None
    current_count = 0
    current_regular: int | None = None
    current_effective: int | None = None
    current_terms: list | None = None
    pending: list[dict] = []

    def flush() -> None:
        nonlocal current_start, current_last, current_count, current_hash
        nonlocal current_regular, current_effective, current_terms
        if current_listing is None or current_hash is None or current_start is None:
            return
        if current_effective is None:
            return
        run_id = listing_run.get(current_listing, 1)
        pending.append(
            {
                "store_listing_id": current_listing,
                "version": 0,  # assigned below per listing
                "started_at": current_start,
                "last_confirmed_at": current_last or current_start,
                "first_run_id": run_id,
                "last_run_id": run_id,
                "confirmation_count": current_count,
                "currency": "BRL",
                "regular_price_cents": current_regular,
                "effective_price_cents": current_effective,
                "price_terms": current_terms or [],
                "state_hash": current_hash,
            }
        )
        current_start = None
        current_last = None
        current_count = 0
        current_hash = None
        current_regular = None
        current_effective = None
        current_terms = None

    for product_id, measure, store_id, observed_at, regular_price, sales_price, offer_tags, tier_prices in rows:
        key = (str(product_id), str(store_id) if store_id else None)
        listing_id = listing_map.get(key)
        if listing_id is None:
            continue
        effective = cents(sales_price)
        if effective is None or effective <= 0:
            # Zero/null/withheld price never creates a period (section 9.4).
            continue
        regular = cents(regular_price)
        if regular is not None and regular <= 0:
            regular = None
        state = price_state(
            regular_price=regular_price,
            effective_price=sales_price,
            tier_prices=tier_prices,
            offer_tags=offer_tags,
            measure=measure,
        )
        state_hash = digest(state)
        terms = [
            {
                "kind": "tier",
                "minimum_quantity": tier["minimum_quantity"],
                "cents": tier["cents"],
                "condition": tier["condition"],
            }
            for tier in state["tier_prices"]
        ]
        terms += [{"kind": "tag", "value": tag} for tag in state["offer_tags"]]
        if listing_id != current_listing:
            flush()
            current_listing = listing_id
            current_hash = state_hash
            current_start = observed_at
            current_last = observed_at
            current_count = 1
            current_regular = regular
            current_effective = effective
            current_terms = terms
        elif state_hash == current_hash:
            current_count += 1
            current_last = observed_at
        else:
            flush()
            current_hash = state_hash
            current_start = observed_at
            current_last = observed_at
            current_count = 1
            current_regular = regular
            current_effective = effective
            current_terms = terms
    flush()

    # Assign monotonic versions per listing and leave the last period open,
    # then bulk-insert in chunks to avoid one INSERT round-trip per period.
    pending.sort(key=lambda row: (row["store_listing_id"], row["started_at"]))
    table = PricePeriod.__table__
    ordered: list[dict] = []
    for _listing_id, periods in groupby(pending, key=lambda row: row["store_listing_id"]):
        periods = list(periods)
        for index, row in enumerate(periods, start=1):
            row["version"] = index
            row["ended_at"] = None if index == len(periods) else periods[index]["started_at"]
            ordered.append(row)

    for start in range(0, len(ordered), 20000):
        db.execute(insert(table), ordered[start : start + 20000])
    return len(ordered)


def backfill_v2(db: Session) -> dict[str, int]:
    """Populate v2 sources, targets, products, listings and price periods."""
    print("backfill-v2: ensuring sources and targets", flush=True)
    sources, _targets, runs = _ensure_infrastructure(db)
    targets_by_source: dict[int, list[CollectionTarget]] = {}
    for target_id in runs:
        target = db.get(CollectionTarget, target_id)
        targets_by_source.setdefault(target.source_id, []).append(target)

    print(f"backfill-v2: creating source products for {len(sources)} sources", flush=True)
    product_mapping = _backfill_products(db, sources, runs, targets_by_source)
    print(f"backfill-v2: {len(product_mapping)} source products", flush=True)
    listing_map, listing_run = _build_listings(db, sources, runs, product_mapping)
    print(f"backfill-v2: {len(listing_map)} listings; rebuilding price periods", flush=True)
    periods = _rebuild_periods(db, listing_map, listing_run)
    db.commit()
    print("backfill-v2: done", flush=True)
    return {
        "sources": len(sources),
        "targets": len(runs),
        "source_products": len(product_mapping),
        "listings": len(listing_map),
        "price_periods": periods,
    }

