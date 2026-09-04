"""Shopping-builder catalog: pickable price lines across all departments.

Combines:
- Açougue lines from the butcher comparison (sale-forms: Peça/Kg, Cubos, ...);
- every other department from a single per-unit pass (R$/kg, R$/L or R$/un).

Each line: {department, category, form (sale-form or unit), label, unit,
sources: {slug: {price, store, sample}}}. The builder search/add works over all
lines so a shopping list can include any classified product.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from app.catalog.v2.read import current_listings
from app.db.models_v2 import LlmCategoryLabel, LlmClassification
from app.enrichment.butcher import butcher_comparison
from app.enrichment.units import UNIT_CATEGORIES, parse_quantity, parse_unit_quantity

_IDX = {"cents": 2, "pid": 7, "raw": 9, "retailer": 14, "store": 15}
_FAMILY_BASE = {"mass": "kg", "vol": "L", "units": "un"}

_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_TTL = 300


def _as_dict_sources(group: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for slug, info in (group.get("sources") or {}).items():
        price = info.get("price_kg") if isinstance(info, dict) else info
        if price is None:
            continue
        out[slug] = {
            "price": float(price),
            "store": info.get("store") if isinstance(info, dict) else None,
            "sample": info.get("sample") if isinstance(info, dict) else None,
        }
    return out


def _butcher_lines(db: Any) -> list[dict[str, Any]]:
    lines = []
    for group in butcher_comparison(db, limit=4000, use_llm=True)["groups"]:
        sources = _as_dict_sources(group)
        if not sources:
            continue
        form = group["form"]
        lines.append(
            {
                "department": "Açougue",
                "category": group["category"],
                "form": form,
                "label": group.get("label") or form,
                "unit": "kg",
                "sources": sources,
            }
        )
    return lines


def _generic_lines(db: Any) -> list[dict[str, Any]]:
    """Per-unit price lines for every department except Açougue (one pass)."""
    accepts = db.execute(
        select(
            LlmClassification.source_product_id,
            LlmClassification.department,
            LlmClassification.line_key,
        ).where(
            LlmClassification.decision == "accept",
            LlmClassification.department != "Açougue",
        )
    ).all()
    overrides = {
        (dept, label): canonical
        for dept, label, canonical in db.execute(
            select(
                LlmCategoryLabel.department,
                LlmCategoryLabel.label,
                LlmCategoryLabel.canonical,
            )
        ).all()
    }
    pid_info: dict[int, tuple[str, str]] = {}
    for pid, dept, label in accepts:
        pid_info[int(pid)] = (dept, overrides.get((dept, label), label))
    pids = set(pid_info)
    if not pids:
        return []

    listings: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in current_listings(db):
        pid = row[_IDX["pid"]]
        if pid not in pids:
            continue
        cents = row[_IDX["cents"]]
        if cents is None or cents <= 0:
            continue
        listings[pid].append(
            (row[_IDX["retailer"]], row[_IDX["store"]], cents / 100.0, row[_IDX["raw"]] or "")
        )

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for pid, listing_list in listings.items():
        dept, canonical = pid_info[pid]
        per_retailer: dict[tuple[str, str], dict[str, Any]] = {}
        for retailer, store, price, raw in listing_list:
            unit = (
                parse_unit_quantity(raw)
                if canonical in UNIT_CATEGORIES
                else parse_quantity(raw)
            )
            if unit is None or unit.amount_base <= 0:
                continue
            key = (retailer, unit.family)
            per = price / unit.amount_base
            current = per_retailer.get(key)
            if current is None or per < current["price"]:
                per_retailer[key] = {
                    "price": per, "store": store, "sample": raw,
                }
        for (retailer, family), info in per_retailer.items():
            gkey = (dept, canonical, family)
            group = groups.setdefault(
                gkey,
                {
                    "products": set(),
                    "sources": {},
                },
            )
            group["products"].add(pid)
            acc = group["sources"].setdefault(
                retailer, {"price": None, "store": None, "sample": None}
            )
            if acc["price"] is None or info["price"] < acc["price"]:
                acc["price"] = info["price"]
                acc["store"] = info["store"]
                acc["sample"] = info["sample"]

    lines = []
    for (dept, canonical, family), group in groups.items():
        sources = {slug: info for slug, info in group["sources"].items() if info["price"] is not None}
        if not sources:
            continue
        unit = _FAMILY_BASE[family]
        lines.append(
            {
                "department": dept,
                "category": canonical,
                "form": unit,  # form = unit for generic departments
                "label": unit,
                "unit": unit,
                "sources": sources,
            }
        )
    return lines


def catalog_rows(db: Any) -> list[dict[str, Any]]:
    """All pickable lines for the shopping builder (cached)."""
    if (
        _CACHE["payload"] is None
        or time.time() - _CACHE["ts"] > _TTL
    ):
        payload = _butcher_lines(db) + _generic_lines(db)
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
    return _CACHE["payload"]


def warm_shop_catalog() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        catalog_rows(db)
