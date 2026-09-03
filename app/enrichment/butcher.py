"""Açougue comparison: group current listings into comparable cuts (R$/kg)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings
from app.enrichment.resolver import MeatItem, group_comparable

# tuple indexes of current_listings row
_IDX = {
    "effective_cents": 2,
    "product_id": 7,
    "raw_name": 9,
    "retailer": 14,
    "store": 15,
}

_CACHE: dict[str, Any] = {"ts": 0.0, "items": 0, "groups": None}


def _compute(db: Session) -> tuple[int, list[dict[str, Any]]]:
    items: list[MeatItem] = []
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]]
        effective = row[_IDX["effective_cents"]]
        if effective is None or effective <= 0:
            continue
        item = MeatItem(
            retailer=row[_IDX["retailer"]],
            store=row[_IDX["store"]],
            product_id=row[_IDX["product_id"]],
            raw_name=raw_name,
            effective_price_cents=effective,
        )
        if item.parsed.is_meat:
            items.append(item)

    groups = group_comparable(items)
    groups = [g for g in groups if any(s["price_kg"] is not None for s in g["sources"].values())]
    groups.sort(
        key=lambda g: (
            -sum(1 for s in g["sources"].values() if s["price_kg"] is not None),
            min(s["price_kg"] for s in g["sources"].values() if s["price_kg"] is not None),
        )
    )
    return len(items), groups


def butcher_comparison(db: Session, limit: int = 300) -> dict[str, Any]:
    """Return grouped Açougue cuts with price per kg per source (TTL cached)."""
    if _CACHE["groups"] is None or time.time() - _CACHE["ts"] > 60:
        _CACHE["items"], _CACHE["groups"] = _compute(db)
        _CACHE["ts"] = time.time()
    return {
        "total_items": _CACHE["items"],
        "total_groups": len(_CACHE["groups"]),
        "groups": _CACHE["groups"][:limit],
    }
