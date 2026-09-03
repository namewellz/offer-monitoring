"""Collect candidate source products for a meat line, with their ids.

The classifier operates on *products* (SourceProduct), not on store listings:
one row per product id, carrying the raw name(s) seen. Retailer can be narrowed
so a run can be done "por supermercado".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings
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
