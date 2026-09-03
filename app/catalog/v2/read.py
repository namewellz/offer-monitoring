"""Read-side queries for the v2 catalog model.

These replace the legacy ``catalog_products``/``catalog_price_observations``
reads with ``store_listings`` + ``price_periods`` (section 15 of the
architecture document). Current state is always the open period of a listing;
changes are computed by comparing the open period with the immediately
preceding period, never from persisted derived columns.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.catalog.taxonomy import canonical_department
from app.db.models import Retailer, Store
from app.db.models_v2 import (
    CatalogSource,
    CollectionTarget,
    PricePeriod,
    SourceProduct,
    SourceProductVersion,
    StoreListing,
)


def _money(cents: int | None) -> Decimal | None:
    if cents is None:
        return None
    return (Decimal(cents) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _change(
    current: Decimal | None, previous: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    if current is None or previous is None or previous <= 0:
        return None, None
    amount = current - previous
    percent = (amount / previous * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return amount, percent


def _terms(terms: Any) -> list[dict[str, Any]]:
    return [term for term in (terms or []) if isinstance(term, dict)]


def _brl(cents: Any) -> str:
    value = _money(cents)
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _condition(
    best_conditional: int | None, terms: Any, regular: Decimal | None, current: Decimal
) -> tuple[str, str]:
    tiers = [t for t in _terms(terms) if t.get("kind") == "tier"]
    tags = [t for t in _terms(terms) if t.get("kind") == "tag"]
    wholesale = [t for t in tiers if t.get("condition") == "wholesale"]
    club = [t for t in tiers if t.get("condition") == "club"]
    app = [t for t in tiers if t.get("condition") == "app"]
    quantity = [
        t
        for t in tiers
        if int(t.get("minimum_quantity") or 1) > 1
        and t.get("condition", "quantity") == "quantity"
    ]
    if best_conditional is not None and not (club or app):
        club = [{"cents": best_conditional}]
    descriptions: list[str] = []
    condition_types: list[str] = []
    if club:
        condition_types.append("club")
        descriptions.extend(_brl(t["cents"]) for t in club if t.get("cents") is not None)
    if wholesale:
        condition_types.append("wholesale")
        descriptions.extend(_brl(t["cents"]) for t in wholesale if t.get("cents") is not None)
    if app:
        condition_types.append("app")
        descriptions.extend(
            f"App a partir de {int(t.get('minimum_quantity') or 1)} un.: {_brl(t['cents'])}"
            for t in app
            if t.get("cents") is not None
        )
    if quantity:
        condition_types.append("quantity")
        descriptions.extend(
            f"A partir de {int(t['minimum_quantity'])} un.: {_brl(t['cents'])}"
            for t in quantity
            if t.get("cents") is not None
        )
    if tags and not descriptions:
        condition_types.append("promotion")
        descriptions.append("Promoção")
    if not descriptions:
        return "Preço final", "final"
    label = " · ".join(descriptions)
    if len(condition_types) > 1:
        return f"Preço condicionado — {label}", "+".join(condition_types)
    kind = condition_types[0]
    labels = {
        "club": f"Preço Clube/Connect — {label}",
        "wholesale": f"Preço atacado — {label}",
        "app": f"Preço exclusivo no App — {label}",
        "quantity": f"Por quantidade — {label}",
        "promotion": f"Preço promocional — {label}",
    }
    return labels[kind], kind


def current_listings(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[tuple[Any, ...]]:
    query = _current_listings_query(product=product, retailer=retailer)
    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)
    return db.execute(query.order_by(SourceProductVersion.raw_name)).all()


def count_current_listings(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
) -> int:
    from sqlalchemy import func

    query = _current_listings_query(product=product, retailer=retailer)
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def _current_listings_query(
    *,
    product: str | None = None,
    retailer: str | None = None,
):
    open_period = aliased(PricePeriod)
    previous = aliased(PricePeriod)
    query = (
        select(
            StoreListing.id,
            open_period.regular_price_cents,
            open_period.effective_price_cents,
            open_period.best_conditional_price_cents,
            open_period.price_terms,
            open_period.last_confirmed_at,
            previous.effective_price_cents,
            SourceProduct.id,
            SourceProduct.external_id,
            SourceProductVersion.raw_name,
            SourceProductVersion.raw_brand,
            SourceProductVersion.raw_gtin,
            SourceProductVersion.raw_categories,
            Retailer.name,
            Retailer.slug,
            Store.name,
        )
        .join(
            open_period,
            and_(
                open_period.store_listing_id == StoreListing.id,
                open_period.ended_at.is_(None),
            ),
        )
        .outerjoin(
            previous,
            and_(
                previous.store_listing_id == StoreListing.id,
                previous.version == open_period.version - 1,
            ),
        )
        .join(SourceProduct, SourceProduct.id == StoreListing.source_product_id)
        .join(
            SourceProductVersion,
            SourceProductVersion.id == SourceProduct.current_version_id,
        )
        .join(CatalogSource, CatalogSource.id == SourceProduct.source_id)
        .join(Retailer, Retailer.id == CatalogSource.retailer_id)
        .join(CollectionTarget, CollectionTarget.id == StoreListing.target_id)
        .join(Store, Store.id == CollectionTarget.store_id)
        .where(StoreListing.active.is_(True))
    )
    if product:
        query = query.where(SourceProductVersion.raw_name.ilike(f"%{product}%"))
    if retailer:
        query = query.where(Retailer.slug == retailer)
    return query


def latest_runs(db: Session) -> list[dict[str, Any]]:
    from app.db.models_v2 import CollectionRun

    ranked = (
        select(
            CollectionRun.id.label("run_id"),
            func.row_number()
            .over(
                partition_by=CollectionRun.target_id,
                order_by=CollectionRun.observed_at.desc(),
            )
            .label("position"),
        )
        .where(CollectionRun.status.in_(("SUCCESS", "PARTIAL_SUCCESS")))
        .subquery()
    )
    rows = db.execute(
        select(CollectionRun, Retailer, Store)
        .join(CollectionTarget, CollectionTarget.id == CollectionRun.target_id)
        .join(CatalogSource, CatalogSource.id == CollectionTarget.source_id)
        .join(Retailer, Retailer.id == CatalogSource.retailer_id)
        .join(Store, Store.id == CollectionTarget.store_id)
        .where(CollectionRun.id.in_(select(ranked.c.run_id).where(ranked.c.position == 1)))
    ).all()
    return [
        {
            "retailer": retailer.name,
            "store": store.name,
            "product_count": run.items_seen,
            "collected_at": run.observed_at,
        }
        for run, retailer, store in rows
    ]


def row_result(row: tuple[Any, ...], department: str | None = None) -> dict[str, Any]:
    (
        listing_id,
        regular_cents,
        effective_cents,
        best_conditional,
        terms,
        observed_at,
        previous_cents,
        product_id,
        external_id,
        raw_name,
        raw_brand,
        raw_gtin,
        raw_categories,
        retailer_name,
        retailer_slug,
        store_name,
    ) = row
    regular = _money(regular_cents)
    current = _money(effective_cents)
    previous_price = _money(previous_cents) if previous_cents is not None else None
    change_amount, change_percent = _change(current, previous_price)
    if department is None:
        department = canonical_department(raw_categories, raw_name)
    price_condition, price_condition_type = _condition(best_conditional, terms, regular, current)
    percent = change_percent
    trend = (
        "sem referência anterior"
        if percent is None
        else "mais caro"
        if percent > 0
        else "mais barato"
        if percent < 0
        else "sem alteração"
    )
    return {
        "product_id": product_id,
        "listing_id": listing_id,
        "external_id": external_id,
        "ean": raw_gtin,
        "product": raw_name,
        "brand": raw_brand,
        "department": department,
        "source_categories": raw_categories,
        "retailer": retailer_name,
        "retailer_slug": retailer_slug,
        "store": store_name,
        "observed_at": observed_at,
        "previous_price": previous_price,
        "regular_price": regular,
        "current_price": current,
        "discount": (
            (regular - current).quantize(Decimal("0.01"))
            if regular is not None and current is not None and regular > current
            else None
        ),
        "change_amount": change_amount,
        "change_percent": percent,
        "price_condition": price_condition,
        "price_condition_type": price_condition_type,
        "trend": trend,
        "summary": (
            f"{raw_name}: {abs(percent):.2f}% {trend}"
            if percent is not None
            else f"{raw_name}: {trend}"
        ),
    }


def _filtered_listings_query(
    *,
    product: str | None,
    retailer: str | None,
    offers_only: bool,
    changes_only: bool,
    direction: str,
    minimum_percent: float,
):
    open_period = aliased(PricePeriod)
    previous = aliased(PricePeriod)
    query = (
        select(
            StoreListing.id,
            open_period.regular_price_cents,
            open_period.effective_price_cents,
            open_period.best_conditional_price_cents,
            open_period.price_terms,
            open_period.last_confirmed_at,
            previous.effective_price_cents,
            SourceProduct.id,
            SourceProduct.external_id,
            SourceProductVersion.raw_name,
            SourceProductVersion.raw_brand,
            SourceProductVersion.raw_gtin,
            SourceProductVersion.raw_categories,
            Retailer.name,
            Retailer.slug,
            Store.name,
        )
        .join(
            open_period,
            and_(
                open_period.store_listing_id == StoreListing.id,
                open_period.ended_at.is_(None),
            ),
        )
        .outerjoin(
            previous,
            and_(
                previous.store_listing_id == StoreListing.id,
                previous.version == open_period.version - 1,
            ),
        )
        .join(SourceProduct, SourceProduct.id == StoreListing.source_product_id)
        .join(
            SourceProductVersion,
            SourceProductVersion.id == SourceProduct.current_version_id,
        )
        .join(CatalogSource, CatalogSource.id == SourceProduct.source_id)
        .join(Retailer, Retailer.id == CatalogSource.retailer_id)
        .join(CollectionTarget, CollectionTarget.id == StoreListing.target_id)
        .join(Store, Store.id == CollectionTarget.store_id)
        .where(StoreListing.active.is_(True))
    )
    if product:
        query = query.where(SourceProductVersion.raw_name.ilike(f"%{product}%"))
    if retailer:
        query = query.where(Retailer.slug == retailer)
    if offers_only:
        query = query.where(
            or_(
                and_(
                    open_period.regular_price_cents.is_not(None),
                    open_period.effective_price_cents < open_period.regular_price_cents,
                ),
                open_period.best_conditional_price_cents.is_not(None),
                func.jsonb_array_length(open_period.price_terms) > 0,
            )
        )
        query = query.order_by(
            (open_period.regular_price_cents - open_period.effective_price_cents)
            .desc()
            .nulls_last(),
            SourceProductVersion.raw_name,
        )
    elif changes_only:
        query = query.where(
            previous.effective_price_cents.is_not(None),
            open_period.effective_price_cents.is_distinct_from(previous.effective_price_cents),
        )
        if minimum_percent > 0:
            query = query.where(
                func.abs(open_period.effective_price_cents - previous.effective_price_cents)
                * 100.0
                >= minimum_percent * previous.effective_price_cents
            )
        if direction == "up":
            query = query.where(open_period.effective_price_cents > previous.effective_price_cents)
        elif direction == "down":
            query = query.where(open_period.effective_price_cents < previous.effective_price_cents)
        query = query.order_by(
            func.abs(
                (open_period.effective_price_cents - previous.effective_price_cents)
                * 1.0
                / previous.effective_price_cents
            )
            .desc()
            .nulls_last(),
            SourceProductVersion.raw_name,
        )
    else:
        query = query.order_by(SourceProductVersion.raw_name)
    return query


def price_results(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    view: str = "all",
) -> list[dict[str, Any]]:
    if direction not in {"all", "up", "down"}:
        raise ValueError("direction must be all, up or down")
    offers_only = view == "offers"
    changes_only = view == "changes"
    query = _filtered_listings_query(
        product=product,
        retailer=retailer,
        offers_only=offers_only,
        changes_only=changes_only,
        direction=direction,
        minimum_percent=minimum_percent,
    )
    results: list[dict[str, Any]] = []
    for row in db.execute(query).all():
        dep = canonical_department(row[12], row[9])
        if department and dep != department:
            continue
        results.append(row_result(row, department=dep))
    return results


def price_result_count(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    view: str = "all",
) -> int:
    return len(
        price_results(
            db,
            product=product,
            retailer=retailer,
            department=department,
            direction=direction,
            minimum_percent=minimum_percent,
            view=view,
        )
    )


def price_history_results(
    db: Session,
    *,
    product_id: int | None = None,
    ean: str | None = None,
    retailer: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    if product_id is None and not ean:
        raise ValueError("product_id or ean is required")
    query = (
        select(PricePeriod, StoreListing, SourceProduct, SourceProductVersion, CatalogSource, Retailer, Store)
        .join(StoreListing, StoreListing.id == PricePeriod.store_listing_id)
        .join(SourceProduct, SourceProduct.id == StoreListing.source_product_id)
        .join(
            SourceProductVersion,
            SourceProductVersion.id == SourceProduct.current_version_id,
        )
        .join(CatalogSource, CatalogSource.id == SourceProduct.source_id)
        .join(Retailer, Retailer.id == CatalogSource.retailer_id)
        .join(CollectionTarget, CollectionTarget.id == StoreListing.target_id)
        .join(Store, Store.id == CollectionTarget.store_id)
    )
    if product_id is not None:
        query = query.where(SourceProduct.id == product_id)
    if ean:
        query = query.where(SourceProductVersion.raw_gtin == ean)
    if retailer:
        query = query.where(Retailer.slug == retailer)
    rows = db.execute(
        query.order_by(PricePeriod.started_at.desc()).limit(min(max(limit, 1), 5000))
    ).all()
    results = []
    for period, listing, product, version, _source, catalog_retailer, store in rows:
        previous = db.scalar(
            select(PricePeriod)
            .where(
                PricePeriod.store_listing_id == listing.id,
                PricePeriod.version == period.version - 1,
            )
        )
        previous_price = _money(previous.effective_price_cents) if previous else None
        current = _money(period.effective_price_cents)
        change_amount, change_percent = _change(current, previous_price)
        results.append(
            {
                "product_id": product.id,
                "listing_id": listing.id,
                "external_id": product.external_id,
                "ean": version.raw_gtin,
                "product": version.raw_name,
                "department": canonical_department(version.raw_categories, version.raw_name),
                "source_categories": version.raw_categories,
                "retailer": catalog_retailer.name,
                "retailer_slug": catalog_retailer.slug,
                "store": store.name,
                "period_id": period.id,
                "version": period.version,
                "started_at": period.started_at,
                "last_confirmed_at": period.last_confirmed_at,
                "ended_at": period.ended_at,
                "confirmation_count": period.confirmation_count,
                "regular_price": _money(period.regular_price_cents),
                "sales_price": current,
                "previous_price": previous_price,
                "change_amount": change_amount,
                "change_percent": change_percent,
            }
        )
    return results


def department_counts(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in current_listings(db):
        department = canonical_department(row[12], row[9])
        counts[department] = counts.get(department, 0) + 1
    return counts
