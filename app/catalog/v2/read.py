"""Read-side queries for the v2 catalog model.

A tela do catálogo lê o **read model** ``store_listings`` (colunas derivadas na
escrita): filtro, contagem, ordenação e paginação acontecem no Postgres e o
Python formata apenas a página visível.

O histórico vem de ``price_periods`` (append-only) e os utilitários de
``current_listings``/``row_result`` continuam existindo para a classificação e
para as telas legadas, que precisam do estado aberto sem a projeção.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.catalog.taxonomy import canonical_department
from app.db.models import Retailer, Store
from app.db.models_v2 import (
    CatalogSource,
    CollectionTarget,
    LlmClassification,
    PricePeriod,
    SourceProduct,
    SourceProductVersion,
    StoreListing,
)
from app.stores import apply_listing_store_filter, apply_store_filter, store_label

# Preço exibido só é considerado válido se foi confirmado há no máximo 2 dias.
# Cada coleta atualiza last_confirmed_at do período aberto, o que valida que o
# preço não mudou desde a última confirmação.
PRICE_MAX_AGE = timedelta(days=2)


def price_fresh_cutoff() -> datetime:
    return datetime.now(timezone.utc) - PRICE_MAX_AGE


def is_price_fresh(confirmed_at: datetime | None) -> bool:
    """True quando o preço foi re-confirmado recentemente (<= 2 dias)."""
    return confirmed_at is not None and confirmed_at >= price_fresh_cutoff()


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


def shelf_previous_cents(
    *,
    current_cents: int | None,
    regular_cents: int | None,
    best_conditional: int | None,
    terms: Any,
    previous_effective: int | None,
    previous_regular: int | None,
) -> int | None:
    """Baseline for a price change.

    When the open price is the shelf price ("preço final") and the previous
    effective price was a discount, compare with the previous shelf price.
    Ending "estilo-dalben" at R$ 11,99 back to R$ 27,99 is not a +133% increase
    if the shelf price only moved from R$ 25,99 to R$ 27,99.
    """
    if previous_effective is None:
        return None
    current_is_final = (
        best_conditional is None
        and not _terms(terms)
        and (regular_cents is None or current_cents == regular_cents)
    )
    if (
        current_is_final
        and previous_regular is not None
        and previous_effective < previous_regular
    ):
        return previous_regular
    return previous_effective


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
    fresh_only: bool = False,
    accepted_only: bool = False,
    ordered: bool = True,
    release: bool = False,
) -> list[tuple[Any, ...]]:
    """Open-period rows for active listings.

    Optional narrowing (all default off, so existing callers are unchanged):

    - ``fresh_only``: only prices confirmed within ``PRICE_MAX_AGE`` (the same
      cut ``is_price_fresh`` applies in Python; callers may keep that check, it
      is only ever stricter because it runs later);
    - ``accepted_only``: only products with at least one LLM ``accept`` verdict;
    - ``ordered=False``: skip ``ORDER BY raw_name`` when the caller does not
      depend on row order;
    - ``release``: end the session transaction right after fetching so a long
      Python pass over the rows does not leave the connection idle in
      transaction. Only use it with a session the caller owns and has no
      pending writes in.
    """
    query = _current_listings_query(
        product=product,
        retailer=retailer,
        fresh_only=fresh_only,
        accepted_only=accepted_only,
    )
    if ordered:
        query = query.order_by(SourceProductVersion.raw_name)
    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)
    rows = db.execute(query).all()
    if release:
        # Não descarta writes pendentes da mesma sessão (ex.: seed de categorias
        # feito antes da leitura): só fecha a transação quando ela é read-only.
        release_read_transaction(db)
    return rows


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
    fresh_only: bool = False,
    accepted_only: bool = False,
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
            store_label(Store),
            open_period.price_basis_unit,
            previous.regular_price_cents,
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
    query = apply_store_filter(query, Store, Retailer)
    if product:
        query = query.where(SourceProductVersion.raw_name.ilike(f"%{product}%"))
    if retailer:
        query = query.where(Retailer.slug == retailer)
    if fresh_only:
        query = query.where(open_period.last_confirmed_at >= price_fresh_cutoff())
    if accepted_only:
        query = query.where(
            StoreListing.source_product_id.in_(
                select(LlmClassification.source_product_id).where(
                    LlmClassification.decision == "accept"
                )
            )
        )
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
        .where(Store.active.is_(True), CollectionTarget.active.is_(True))
    ).all()
    return [
        {
            "retailer": retailer.name,
            "store": store.display_name or store.name,
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
        *_extra,  # price_basis_unit (17th column) is not used here
    ) = row
    regular = _money(regular_cents)
    current = _money(effective_cents)
    previous_regular = _extra[-1] if _extra and isinstance(_extra[-1], int) else None
    baseline_cents = shelf_previous_cents(
        current_cents=effective_cents,
        regular_cents=regular_cents,
        best_conditional=best_conditional,
        terms=terms,
        previous_effective=previous_cents,
        previous_regular=previous_regular,
    )
    previous_price = _money(baseline_cents) if baseline_cents is not None else None
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


def price_results(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    view: str = "all",
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Página (ou série) do read model, filtrada e ordenada no Postgres."""
    if direction not in {"all", "up", "down"}:
        raise ValueError("direction must be all, up or down")
    query = _listing_query(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        view=view,
    )
    if offset:
        query = query.offset(max(offset, 0))
    if limit is not None:
        query = query.limit(max(limit, 1))
    listings = db.scalars(query).all()
    results = [listing_result(listing) for listing in listings]
    release_read_transaction(db)
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
    if direction not in {"all", "up", "down"}:
        raise ValueError("direction must be all, up or down")
    conditions = _listing_conditions(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        view=view,
    )
    query = select(func.count()).select_from(StoreListing).where(*conditions)
    query = apply_listing_store_filter(query, StoreListing)
    total = int(db.scalar(query) or 0)
    release_read_transaction(db)
    return total


# ---------------------------------------------------------------------------
# Read model: a tela lê ``store_listings`` sozinho.
#
# Tudo o que a página precisa (departamento, nome, preço, variação, loja) já foi
# derivado no ingest. Aqui só existem WHERE/ORDER BY/LIMIT em SQL e a formatação
# dos ~100 registros da página — nunca um filtro em Python sobre a base inteira.
# ---------------------------------------------------------------------------


def _listing_conditions(
    *,
    product: str | None,
    retailer: str | None,
    department: str | None,
    direction: str,
    minimum_percent: float,
    view: str,
) -> list[Any]:
    conditions: list[Any] = [
        StoreListing.active.is_(True),
        # Paridade com o antigo INNER JOIN no período aberto: listing sem preço
        # conhecido não aparece na tela (e não tem last_confirmed_at).
        StoreListing.effective_price_cents.is_not(None),
    ]
    if product:
        conditions.append(StoreListing.product_name.ilike(f"%{product}%"))
    if retailer:
        conditions.append(StoreListing.retailer_slug == retailer)
    if department:
        conditions.append(StoreListing.department == department)
    if view == "offers":
        conditions.append(StoreListing.is_offer.is_(True))
    else:
        if view == "changes":
            conditions.append(StoreListing.change_percent.is_not(None))
            conditions.append(StoreListing.change_percent != 0)
        if minimum_percent > 0:
            conditions.append(func.abs(StoreListing.change_percent) >= minimum_percent)
        if direction == "up":
            conditions.append(StoreListing.change_percent > 0)
        elif direction == "down":
            conditions.append(StoreListing.change_percent < 0)
    return conditions


def _listing_ordering(view: str) -> tuple[Any, ...]:
    if view == "offers":
        return (
            (StoreListing.regular_price_cents - StoreListing.effective_price_cents)
            .desc()
            .nulls_last(),
            StoreListing.product_name,
        )
    if view == "changes":
        return (
            func.abs(StoreListing.change_percent).desc().nulls_last(),
            StoreListing.product_name,
        )
    return (StoreListing.product_name,)


def _listing_query(
    *,
    product: str | None,
    retailer: str | None,
    department: str | None,
    direction: str,
    minimum_percent: float,
    view: str,
):
    """SELECT sobre o read model, já com os filtros de loja do contexto."""
    conditions = _listing_conditions(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        view=view,
    )
    query = select(StoreListing).where(*conditions)
    query = apply_listing_store_filter(query, StoreListing)
    return query.order_by(*_listing_ordering(view))


def listing_result(listing: StoreListing) -> dict[str, Any]:
    """Formata uma linha do read model no dicionário que a tela/CSV consomem."""
    regular = _money(listing.regular_price_cents)
    current = _money(listing.effective_price_cents)
    previous_price = _money(listing.previous_cents)
    change_amount = _money(listing.change_amount_cents)
    change_percent = (
        Decimal(listing.change_percent) if listing.change_percent is not None else None
    )
    price_condition, price_condition_type = _condition(
        listing.best_conditional_cents, listing.price_terms, regular, current
    )
    trend = (
        "sem referência anterior"
        if change_percent is None
        else "mais caro"
        if change_percent > 0
        else "mais barato"
        if change_percent < 0
        else "sem alteração"
    )
    product_name = listing.product_name or ""
    return {
        "product_id": listing.source_product_id,
        "listing_id": listing.id,
        "external_id": listing.product_external_id,
        "ean": listing.product_gtin,
        "product": product_name,
        "brand": listing.product_brand,
        "department": listing.department or "Outros",
        "source_categories": listing.product_categories or [],
        "retailer": listing.retailer_name or "",
        "retailer_slug": listing.retailer_slug or "",
        "store": listing.store_name,
        "observed_at": listing.last_confirmed_at,
        "previous_price": previous_price,
        "regular_price": regular,
        "current_price": current,
        "discount": (
            (regular - current).quantize(Decimal("0.01"))
            if regular is not None and current is not None and regular > current
            else None
        ),
        "change_amount": change_amount,
        "change_percent": change_percent,
        "price_condition": price_condition,
        "price_condition_type": price_condition_type,
        "trend": trend,
        "summary": (
            f"{product_name}: {abs(change_percent):.2f}% {trend}"
            if change_percent is not None
            else f"{product_name}: {trend}"
        ),
        "is_offer": bool(listing.is_offer),
        "offer_kind": listing.offer_kind,
    }


def release_read_transaction(db: Session) -> None:
    """Fecha a transação de leitura sem descartar writes pendentes.

    Sem isso a conexão fica ``idle in transaction`` enquanto o template/CSV é
    montado, o que já travou ``CREATE INDEX CONCURRENTLY`` em produção.
    """
    if db.new or db.dirty or db.deleted:
        return
    db.rollback()


def price_page(
    db: Session,
    *,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    view: str = "all",
    limit: int = 100,
    offset: int = 0,
    with_total: bool = True,
) -> tuple[int | None, list[dict[str, Any]]]:
    """Uma página do read model + total, tudo calculado no Postgres."""
    if direction not in {"all", "up", "down"}:
        raise ValueError("direction must be all, up or down")
    query = _listing_query(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        view=view,
    )
    total: int | None = None
    if with_total:
        conditions = _listing_conditions(
            product=product,
            retailer=retailer,
            department=department,
            direction=direction,
            minimum_percent=minimum_percent,
            view=view,
        )
        count_query = select(func.count()).select_from(StoreListing).where(*conditions)
        count_query = apply_listing_store_filter(count_query, StoreListing)
        total = int(db.scalar(count_query) or 0)
    listings = db.scalars(
        query.offset(max(offset, 0)).limit(max(limit, 1))
    ).all()
    results = [listing_result(listing) for listing in listings]
    # Formata antes de fechar: rollback expira os objetos e cada atributo lido
    # depois dispararia um SELECT novo.
    release_read_transaction(db)
    return total, results


def listing_department_counts(db: Session) -> dict[str, int]:
    """Contagem por departamento em um GROUP BY indexado."""
    query = select(StoreListing.department, func.count()).where(
        StoreListing.active.is_(True)
    )
    query = apply_listing_store_filter(query, StoreListing)
    rows = db.execute(query.group_by(StoreListing.department)).all()
    release_read_transaction(db)
    return {(department or "Outros"): int(count) for department, count in rows}


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
                "department": version.department
                or canonical_department(version.raw_categories, version.raw_name),
                "source_categories": version.raw_categories,
                "retailer": catalog_retailer.name,
                "retailer_slug": catalog_retailer.slug,
                "store": store.display_name or store.name,
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
    return listing_department_counts(db)
