"""Collect candidate source products for a meat line, with their ids.

The classifier operates on *products* (SourceProduct), not on store listings:
one row per product id, carrying the raw name(s) seen. Retailer can be narrowed
so a run can be done "por supermercado".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.catalog.v2.read import current_listings
from app.db.models_v2 import LlmClassification
from app.enrichment.text import fold

# tuple indexes of current_listings row (see app/catalog/v2/read.py)
_IDX = {
    "effective_cents": 2,
    "product_id": 7,
    "raw_name": 9,
    "retailer": 14,
    "store": 15,
}


def collect_candidates(
    db: Session,
    keywords: tuple[str, ...],
    retailer: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Products whose current raw name mentions one of ``keywords``.

    Returns one dict per product id::

        {"product_id": int, "raw_name": str, "retailer": str,
         "store": str | None, "price_kg": float | None}
    """
    keys = tuple(fold(k) for k in keywords)
    by_product: dict[int, dict[str, Any]] = {}
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]] or ""
        effective = row[_IDX["effective_cents"]]
        retailer_slug = row[_IDX["retailer"]]
        if retailer is not None and retailer_slug != retailer:
            continue
        if effective is None or effective <= 0:
            continue
        folded = fold(raw_name)
        if not any(key in folded for key in keys):
            continue
        pid = row[_IDX["product_id"]]
        entry = by_product.get(pid)
        if entry is None:
            by_product[pid] = {
                "product_id": pid,
                "raw_name": raw_name,
                "retailer": retailer_slug,
                "store": row[_IDX["store"]],
            }
        elif raw_name != entry["raw_name"] and len(entry["raw_name"]) < len(raw_name):
            # keep the most descriptive spelling seen for the same product
            entry["raw_name"] = raw_name
    ordered = sorted(by_product.values(), key=lambda p: (p["retailer"], p["raw_name"]))
    return ordered[:limit] if limit else ordered


def collect_department_candidates(
    db: Session,
    department: str,
    retailer: str | None = None,
    limit: int | None = None,
    exclude_accepted: bool = True,
) -> list[dict[str, Any]]:
    """Products that belong to a store department (taxonomy), one row per id.

    Pool = priced products whose deterministic department (source categories +
    raw name) equals ``department`` — including the false positives the LLM
    must reject. When ``exclude_accepted`` (default) products already accepted
    in *another* department are skipped, so each product is classified once
    (evita dupla classificação e preserva o Açougue já feito).
    """
    accepted_elsewhere: set[int] = set()
    if exclude_accepted:
        accepted_elsewhere = set(
            db.scalars(
                select(LlmClassification.source_product_id).where(
                    LlmClassification.decision == "accept",
                    LlmClassification.department != department,
                )
            ).all()
        )

    by_product: dict[int, dict[str, Any]] = {}
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]] or ""
        effective = row[_IDX["effective_cents"]]
        retailer_slug = row[_IDX["retailer"]]
        if retailer is not None and retailer_slug != retailer:
            continue
        if effective is None or effective <= 0:
            continue
        raw_categories = row[12]
        if isinstance(raw_categories, str):
            raw_categories = [raw_categories] if raw_categories else []
        elif raw_categories is None:
            raw_categories = []
        else:
            raw_categories = list(raw_categories)
        if canonical_department(raw_categories, raw_name) != department:
            continue
        pid = row[_IDX["product_id"]]
        if pid in accepted_elsewhere:
            continue
        entry = by_product.get(pid)
        if entry is None:
            by_product[pid] = {
                "product_id": pid,
                "raw_name": raw_name,
                "retailer": retailer_slug,
                "store": row[_IDX["store"]],
            }
        elif len(raw_name) > len(entry["raw_name"]):
            entry["raw_name"] = raw_name
    ordered = sorted(by_product.values(), key=lambda p: (p["retailer"], p["raw_name"]))
    return ordered[:limit] if limit else ordered


def collect_meat_candidates(
    db: Session,
    retailer: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """All priced products that look like Açougue (meat-ish), one row per id.

    An item is included when the deterministic parser considers it meat
    (species+cut) OR its raw name mentions a cut/species/type — i.e. the pool we
    want the LLM to review, including the false positives we want it to reject.
    """
    from app.enrichment.meat import parse_meat
    from app.enrichment.review import _mentions_meat

    by_product: dict[int, dict[str, Any]] = {}
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]] or ""
        effective = row[_IDX["effective_cents"]]
        retailer_slug = row[_IDX["retailer"]]
        if retailer is not None and retailer_slug != retailer:
            continue
        if effective is None or effective <= 0:
            continue
        parsed = parse_meat(raw_name)
        if not (parsed.is_meat or _mentions_meat(raw_name)):
            continue
        pid = row[_IDX["product_id"]]
        entry = by_product.get(pid)
        if entry is None:
            by_product[pid] = {
                "product_id": pid,
                "raw_name": raw_name,
                "retailer": retailer_slug,
            }
        elif len(raw_name) > len(entry["raw_name"]):
            entry["raw_name"] = raw_name
    ordered = sorted(by_product.values(), key=lambda p: (p["retailer"], p["raw_name"]))
    return ordered[:limit] if limit else ordered
