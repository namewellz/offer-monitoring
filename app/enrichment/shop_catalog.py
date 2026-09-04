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
from app.enrichment.produce import normalize_produce
from app.enrichment.units import (
    PACKAGE_CATEGORIES,
    parse_package_quantity,
    parse_quantity,
)

_IDX = {"cents": 2, "pid": 7, "raw": 9, "retailer": 14, "store": 15}
_FAMILY_BASE = {"mass": "kg", "vol": "L", "units": "un", "package": "pacote"}

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
            LlmClassification.department.notin_(("Açougue", "Hortifruti")),
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
                parse_package_quantity(raw)
                if canonical in PACKAGE_CATEGORIES
                else parse_quantity(raw)
            )
            if unit is None or unit.amount_base <= 0:
                continue
            key = (retailer, unit.family)
            per = price / unit.amount_base
            current = per_retailer.get(key)
            if current is None or per < current["price"]:
                per_retailer[key] = {
                    "price": per,
                    "store": store,
                    "sample": raw,
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
        sources = {
            slug: info for slug, info in group["sources"].items() if info["price"] is not None
        }
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


def _group_produce(
    entries: list[tuple[int, float, str, str, str]],
    canonical: dict[int, str],
) -> list[dict[str, Any]]:
    """Group Hortifrúti listings into pickable lines (pure, DB-free).

    Each listing entry is (pid, price, raw, retailer, store). Product rows are
    keyed by the canonical produce identity ("Maçã Fuji") when the raw name is
    recognized by the produce normalizer; unrecognized products fall back to
    the classification canonical category (ex.: "Ovo de Granja"). Lines keep
    the sale-unit family (kg / L / un) as the ``form`` so the same product can
    be offered both per kg and per unidade.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for pid, price, raw, retailer, store in entries:
        prod = normalize_produce(raw)
        name = prod.product if prod is not None else canonical.get(pid)
        if not name:
            continue
        unit = parse_quantity(raw)
        if unit is None or unit.amount_base <= 0:
            continue
        per = price / unit.amount_base
        gkey = (name, unit.family)
        group = groups.setdefault(gkey, {"products": set(), "sources": {}})
        group["products"].add(pid)
        acc = group["sources"].setdefault(retailer, {"price": None, "store": None, "sample": None})
        if acc["price"] is None or per < acc["price"]:
            acc["price"] = per
            acc["store"] = store
            acc["sample"] = raw

    order = {"mass": 0, "vol": 1, "units": 2, "package": 3}
    lines = []
    for (name, family), group in groups.items():
        sources = {
            slug: info for slug, info in group["sources"].items() if info["price"] is not None
        }
        if not sources:
            continue
        unit = _FAMILY_BASE[family]
        lines.append(
            {
                "department": "Hortifruti",
                "category": name,
                "form": unit,  # form = sale-unit family (kg / L / un)
                "label": unit,
                "unit": unit,
                "sources": sources,
                "products": len(group["products"]),
            }
        )
    lines.sort(key=lambda line: (line["category"].lower(), order.get(line["form"], 99)))
    return lines


def _produce_lines(db: Any) -> list[dict[str, Any]]:
    """Pickable Hortifrúti lines: produce identity products per sale unit."""
    accepts = db.execute(
        select(
            LlmClassification.source_product_id,
            LlmClassification.line_key,
        ).where(
            LlmClassification.decision == "accept",
            LlmClassification.department == "Hortifruti",
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
    pid_canon: dict[int, str] = {}
    for pid, label in accepts:
        pid_canon[int(pid)] = overrides.get(("Hortifruti", label), label)
    pids = set(pid_canon)
    if not pids:
        return []

    entries: list[tuple[int, float, str, str, str]] = []
    for row in current_listings(db):
        pid = row[_IDX["pid"]]
        if pid not in pids:
            continue
        cents = row[_IDX["cents"]]
        if cents is None or cents <= 0:
            continue
        entries.append(
            (
                pid,
                cents / 100.0,
                row[_IDX["raw"]] or "",
                row[_IDX["retailer"]],
                row[_IDX["store"]] or "",
            )
        )
    return _group_produce(entries, pid_canon)


def catalog_rows(db: Any) -> list[dict[str, Any]]:
    """All pickable lines for the shopping builder (cached)."""
    if _CACHE["payload"] is None or time.time() - _CACHE["ts"] > _TTL:
        payload = _butcher_lines(db) + _produce_lines(db) + _generic_lines(db)
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
    return _CACHE["payload"]


def warm_shop_catalog() -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        catalog_rows(db)
