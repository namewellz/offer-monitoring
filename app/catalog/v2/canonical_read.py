"""Leitura da lista canônica — uma tabela, sem joins.

Tudo o que a tela precisa já está projetado em ``store_listings`` pelo
normalizador determinístico (sem LLM): ``identity_key``, ``canonical_name``,
``coverage_group``, ``comparison_quantity/unit`` e ``unit_price_micros``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.v2.read import release_read_transaction
from app.db.models_v2 import CanonicalProduct, StoreListing

# Grupos em que a identidade canônica é confiável para comparação.
COMPARABLE_GROUPS = ("A1", "A2")


def _unit_label(micros: int | None, unit: str | None) -> tuple[str, float | None]:
    """Converte micro-reais por unidade base no preço por kg / L / unidade."""
    if micros is None or unit is None:
        return "—", None
    value = micros * 1000 / 1_000_000 if unit in ("g", "ml") else micros / 1_000_000
    if unit == "g":
        return "kg", value
    if unit == "ml":
        return "L", value
    return "un", value


def canonical_products(
    db: Session,
    *,
    product: str | None = None,
    department: str | None = None,
    only_covered: bool = False,
    limit: int = 100,
    offset: int = 0,
    with_total: bool = True,
) -> tuple[int | None, list[dict[str, Any]]]:
    """Uma linha por produto canônico, lida da tabela agregada.

    ``canonical_products`` é reconstruída ao fim de cada projeção — a requisição
    não agrega nada, só filtra e ordena uma tabela de ~150k linhas.
    """
    conditions: list[Any] = []
    if product:
        conditions.append(CanonicalProduct.canonical_name.ilike(f"%{product}%"))
    if department:
        conditions.append(CanonicalProduct.department == department)
    if only_covered:
        conditions.append(CanonicalProduct.coverage_group.in_(COMPARABLE_GROUPS))

    total: int | None = None
    if with_total:
        total = int(
            db.scalar(
                select(func.count())
                .select_from(CanonicalProduct)
                .where(*conditions)
            )
            or 0
        )

    rows = db.execute(
        select(CanonicalProduct)
        .where(*conditions)
        .order_by(CanonicalProduct.offers.desc(), CanonicalProduct.canonical_name)
        .offset(max(offset, 0))
        .limit(max(limit, 1))
    ).scalars().all()

    results = []
    for row in rows:
        unit_name, min_value = _unit_label(
            row.min_unit_price_micros, row.comparison_unit
        )
        _, max_value = _unit_label(row.max_unit_price_micros, row.comparison_unit)
        results.append(
            {
                "identity_key": row.identity_key,
                "canonical_name": row.canonical_name or row.identity_key,
                "department": row.department or "Outros",
                "offers": int(row.offers),
                "retailers": int(row.retailers),
                "coverage_group": row.coverage_group,
                "unit": unit_name,
                "min_unit_price": min_value,
                "max_unit_price": max_value,
                "spread_percent": (
                    round((max_value - min_value) / min_value * 100, 2)
                    if min_value and max_value and min_value > 0
                    else None
                ),
            }
        )
    release_read_transaction(db)
    return total, results


def canonical_offers(
    db: Session, identity_key: str, *, limit: int = 200
) -> dict[str, Any]:
    """Todas as ofertas de um produto canônico, da mais barata para a mais cara."""
    rows = db.execute(
        select(StoreListing)
        .where(
            StoreListing.active,
            StoreListing.identity_key == identity_key,
            StoreListing.effective_price_cents.is_not(None),
        )
        .order_by(
            StoreListing.last_confirmed_at.desc().nulls_last(),
            StoreListing.unit_price_micros.asc().nulls_last(),
            StoreListing.effective_price_cents,
        )
    ).scalars().all()

    # A mesma oferta pode existir em dois catálogos do mesmo alvo de coleta
    # (ids externos diferentes). Fica só a observação mais recente.
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for listing in rows:
        key = (
            listing.retailer_slug or "",
            listing.store_name or "",
            listing.product_name or "",
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(listing)
    unique.sort(
        key=lambda listing: (
            listing.unit_price_micros is None,
            listing.unit_price_micros or 0,
            listing.effective_price_cents or 0,
        )
    )
    unique = unique[: max(limit, 1)]

    offers = []
    for listing in unique:
        unit_name, unit_value = _unit_label(
            listing.unit_price_micros, listing.comparison_unit
        )
        offers.append(
            {
                "listing_id": listing.id,
                "product_name": listing.product_name,
                "brand": listing.product_brand,
                "department": listing.department,
                "retailer": listing.retailer_name,
                "retailer_slug": listing.retailer_slug,
                "store": listing.store_name,
                "price": (Decimal(listing.effective_price_cents) / 100)
                if listing.effective_price_cents is not None
                else None,
                "regular_price": (Decimal(listing.regular_price_cents) / 100)
                if listing.regular_price_cents is not None
                else None,
                "comparison_quantity": listing.comparison_quantity,
                "base_unit": listing.comparison_unit,
                "unit": unit_name,
                "unit_price": unit_value,
                "coverage_group": listing.coverage_group,
                "observed_at": listing.last_confirmed_at,
                "is_offer": bool(listing.is_offer),
            }
        )
    canonical_name = next((o["product_name"] for o in offers), identity_key)
    head = unique[0] if unique else None
    release_read_transaction(db)
    return {
        "identity_key": identity_key,
        "canonical_name": (head.canonical_name if head else None) or canonical_name,
        "department": (head.department if head else None),
        "coverage_group": (head.coverage_group if head else None),
        "comparison_quantity": (head.comparison_quantity if head else None),
        "comparison_unit": (head.comparison_unit if head else None),
        "offers": offers,
        "observed_at": (head.last_confirmed_at if head else None),
    }


def canonical_stats(db: Session) -> dict[str, Any]:
    """Cobertura: identidade e preço unitário por grupo."""
    rows = db.execute(
        select(
            StoreListing.coverage_group,
            func.count().label("listings"),
            func.count(StoreListing.unit_price_micros).label("priced"),
        )
        .where(StoreListing.active, StoreListing.identity_key.is_not(None))
        .group_by(StoreListing.coverage_group)
    ).all()
    by_group = {(group or "?"): int(listings) for group, listings, _ in rows}
    priced_by_group = {(group or "?"): int(priced) for group, _, priced in rows}

    total, priced_total = db.execute(
        select(
            func.count(),
            func.count(StoreListing.effective_price_cents),
        ).where(StoreListing.active)
    ).one()
    comparable = sum(by_group.get(group, 0) for group in COMPARABLE_GROUPS)
    projected = sum(by_group.values())
    priced = sum(priced_by_group.values())
    release_read_transaction(db)
    return {
        "listings_total": int(total or 0),
        "listings_priced": int(priced_total or 0),
        "listings_with_identity": projected,
        "listings_comparable": comparable,
        "listings_with_unit_price": priced,
        "coverage_percent": round(priced / priced_total * 100, 1) if priced_total else 0.0,
        "by_group": by_group,
        "priced_by_group": priced_by_group,
    }
