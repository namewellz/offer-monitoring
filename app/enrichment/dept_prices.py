"""Per-department price comparison (R$ per unit) over LLM-accepted products.

For a department, accepted products (llm_classifications) are grouped by
canonical category. Each store listing of those products is normalized to a
price *per unit* (R$/kg, R$/L or R$/un) using :mod:`app.enrichment.units`, then
per retailer the best store price is kept and categories are ordered by their
cheapest source — mirroring the Açougue cuts screen, but unit-aware and generic.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select

from app.catalog.v2.read import current_listings
from app.classification.canonical import canonical_map
from app.db.models_v2 import LlmClassification
from app.enrichment.units import (
    PACKAGE_CATEGORIES,
    parse_package_quantity,
    parse_quantity,
)

_IDX = {
    "cents": 2,
    "pid": 7,
    "raw": 9,
    "retailer": 14,
    "store": 15,
}

_FAMILY_BASE = {"mass": "kg", "vol": "L", "units": "un", "package": "pacote"}
_FAMILY_ORDER = {"mass": 0, "vol": 1, "units": 2, "package": 3}

# TTL cache, same philosophy as butcher comparison (warmed by api startup thread).
_CACHE: dict[str, Any] = {"key": None, "payload": None, "ts": 0.0}
_TTL = 300


def dept_price_rows(db: Any, department: str) -> dict[str, Any]:
    """Price rows per (canonical category, unit family) for a department."""
    import time

    cache_key = f"{department}|llm"
    if (
        _CACHE["key"] != cache_key
        or _CACHE["payload"] is None
        or time.time() - _CACHE["ts"] > _TTL
    ):
        payload = _compute(db, department)
        _CACHE["key"] = cache_key
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
    return _CACHE["payload"]


def warm_department_prices(department: str = "Mercearia") -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        dept_price_rows(db, department)


def _compute(db: Any, department: str) -> dict[str, Any]:
    accepts = db.execute(
        select(
            LlmClassification.source_product_id,
            LlmClassification.line_key,
        ).where(
            LlmClassification.department == department,
            LlmClassification.decision == "accept",
        )
    ).all()
    overrides = canonical_map(db, department=department)
    pid_canon: dict[int, str] = {}
    for pid, label in accepts:
        pid_canon[int(pid)] = overrides.get(label, label)
    pids = set(pid_canon)
    if not pids:
        return {
            "department": department,
            "groups": [],
            "accepted_products": 0,
            "priced_products": 0,
            "unparsed_products": 0,
        }

    listings_by_pid: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in current_listings(db):
        pid = row[_IDX["pid"]]
        if pid not in pids:
            continue
        cents = row[_IDX["cents"]]
        if cents is None or cents <= 0:
            continue
        listings_by_pid[pid].append(
            (row[_IDX["retailer"]], row[_IDX["store"]], cents / 100.0, row[_IDX["raw"]] or "")
        )

    # (canonical, family) -> accumulator
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    priced_products = 0
    unparsed_products = 0

    for pid, listing_list in listings_by_pid.items():
        canon_cat = pid_canon[pid]
        parsed = []  # (retailer, store, per_base, family, raw)
        for retailer, store, price, raw in listing_list:
            unit = (
                parse_package_quantity(raw)
                if canon_cat in PACKAGE_CATEGORIES
                else parse_quantity(raw)
            )
            if unit is None or unit.amount_base <= 0:
                continue
            parsed.append(
                (retailer, store, price / unit.amount_base, unit.family, raw)
            )
        if not parsed:
            unparsed_products += 1
            continue
        priced_products += 1
        # best store price per retailer, split by unit family
        best_per_retailer: dict[tuple[str, str], dict[str, Any]] = {}
        for retailer, store, per, family, raw in parsed:
            key = (retailer, family)
            current = best_per_retailer.get(key)
            if current is None or per < current["per"]:
                best_per_retailer[key] = {
                    "per": per, "store": store, "sample": raw,
                }
        for (retailer, family), info in best_per_retailer.items():
            gkey = (canon_cat, family)
            group = groups.setdefault(
                gkey,
                {
                    "canonical": canon_cat,
                    "family": family,
                    "unit": _FAMILY_BASE[family],
                    "products": set(),
                    "per_retailer": {},
                },
            )
            group["products"].add(pid)
            acc = group["per_retailer"].setdefault(
                retailer, {"price": None, "store": None, "sample": None}
            )
            if acc["price"] is None or info["per"] < acc["price"]:
                acc["price"] = info["per"]
                acc["store"] = info["store"]
                acc["sample"] = info["sample"]

    group_rows = []
    for (canonical, family), group in groups.items():
        sources = []
        for slug, info in group["per_retailer"].items():
            if info["price"] is None:
                continue
            sources.append(
                {
                    "slug": slug,
                    "price": round(info["price"], 4),
                    "store": info["store"],
                    "sample": info["sample"],
                }
            )
        sources.sort(key=lambda s: s["price"])
        group_rows.append(
            {
                "canonical": canonical,
                "family": family,
                "unit": _FAMILY_BASE[family],
                "products": len(group["products"]),
                "sources": sources,
            }
        )
    group_rows.sort(
        key=lambda g: (
            g["canonical"].lower(),
            _FAMILY_ORDER.get(g["family"], 99),
        )
    )
    return {
        "department": department,
        "groups": group_rows,
        "accepted_products": len(pids),
        "priced_products": priced_products,
        "unparsed_products": unparsed_products,
    }
