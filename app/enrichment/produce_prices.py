"""Where-to-buy-cheapest comparison for produce (hortifrúti) products.

Answer the goal "onde devo comprar o produto X mais barato": accepted
Hortifrúti products are mapped through :mod:`app.enrichment.produce` to a
canonical identity (FRUIT + VARIETY, ex.: "Maçã Fuji") that is decoupled from
the sale presentation. Every listing of every product that maps to the same
identity is normalized to a price per kg (R$/kg) using its weight/sale form,
then per retailer the best store is kept and identities are ordered by their
cheapest source — the store to buy each product at.

Products whose listing cannot be normalized to per kg (e.g. sold only per
"unidade" with no weight) are kept in a secondary "per unidade" list so they
are never silently lost.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from app.catalog.v2.read import current_listings
from app.db.models_v2 import LlmClassification
from app.enrichment.produce import normalize_produce
from app.enrichment.units import PACKAGE_CATEGORIES

_IDX = {"cents": 2, "pid": 7, "raw": 9, "retailer_name": 13, "retailer": 14, "store": 15}

_CACHE: dict[str, Any] = {"key": None, "payload": None, "ts": 0.0}
_TTL = 300


def _weight_label(weight_g: float | None, form: str) -> str:
    if weight_g and weight_g > 0:
        if weight_g >= 1000:
            whole = weight_g / 1000.0
            return f"{whole:g}kg" if float(whole).is_integer() else f"{whole:g} kg"
        return f"{weight_g:g} g"
    return ""


def _presentation_label(form: str, weight_g: float | None) -> str:
    """Human label for the sale presentation, ex.: 'bandeja 600 g' / 'kg'."""
    weight = _weight_label(weight_g, form)
    if weight:
        if form in ("", "Kg"):
            return weight
        return f"{form.lower()} {weight}"
    if form:
        return form.lower()
    return ""


def _per_kg(price: float, form: str, weight_g: float | None) -> float | None:
    """Price normalized to R$/kg when the weight/sale form allows it."""
    if weight_g and weight_g > 0:
        return price / (weight_g / 1000.0)
    if form == "Kg":
        # "Maçã Fuji Kg" -> implicit 1 kg
        return price
    return None


def _aggregate(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Group listing entries by canonical produce identity and rank retailers.

    ``entries`` items: {pid, price, raw, retailer, retailer_name, store}.
    Pure and DB-free so it can be unit tested.

    Products in :data:`PACKAGE_CATEGORIES` (Morango, Pão de Alho…) are sold per
    package/bandeja, never by weight: their price is kept per package and their
    identity is flagged ``is_package`` so the UI shows R$/pacote.
    """
    groups: dict[str, dict[str, Any]] = {}
    unmodeled = 0

    for entry in entries:
        prod = normalize_produce(entry["raw"])
        if prod is None:
            unmodeled += 1
            continue
        price = entry["price"]
        product = prod.product
        acc = groups.setdefault(
            product,
            {
                "product": product,
                "fruit": prod.fruit,
                "variety": prod.variety,
                "pids": set(),
                "kg": {},
                "unit": {},
                "is_package": False,
            },
        )
        acc["pids"].add(int(entry["pid"]))
        row = {
            "slug": entry["retailer"],
            "label": entry["retailer_name"] or entry["retailer"],
            "store": entry["store"],
            "sample": entry["raw"],
            "price": price,
        }
        if product in PACKAGE_CATEGORIES:
            # vendido por pacote/bandeja: compara-se o preço do pacote inteiro
            acc["is_package"] = True
            row["per_kg"] = None
            row["per_pkg"] = price
            row["presentation"] = "pacote"
            bucket = acc["unit"]
            current = bucket.get(row["slug"])
            if current is None or price < current["price"]:
                bucket[row["slug"]] = row
            continue

        per_kg = _per_kg(price, prod.form, prod.weight_g)
        row["per_kg"] = per_kg
        row["presentation"] = _presentation_label(prod.form, prod.weight_g)
        bucket = acc["kg"] if per_kg is not None else acc["unit"]
        current = bucket.get(row["slug"])
        if current is None:
            bucket[row["slug"]] = row
            continue
        # keep the cheapest per-kg for ranking; for per-unit keep cheapest price
        if per_kg is not None and per_kg < current["per_kg"]:
            bucket[row["slug"]] = row
        elif per_kg is None and price < current["price"]:
            bucket[row["slug"]] = row

    identities: list[dict[str, Any]] = []
    for acc in groups.values():
        base = {
            "product": acc["product"],
            "fruit": acc["fruit"],
            "variety": acc["variety"],
            "products": len(acc["pids"]),
            "is_package": acc["is_package"],
        }
        if acc["is_package"]:
            pkg_rows = sorted(acc["unit"].values(), key=lambda r: r["price"])
            best = pkg_rows[0] if pkg_rows else None
            identities.append(
                {
                    **base,
                    "has_kg": False,
                    "best": best,
                    "cheapest": (
                        {
                            "price": best["per_pkg"],
                            "label": best["label"],
                            "store": best["store"],
                            "sample": best["sample"],
                            "presentation": best["presentation"],
                        }
                        if best
                        else None
                    ),
                    "retailers": pkg_rows,
                    "unit_only": [],
                }
            )
            continue
        kg_rows = sorted(
            acc["kg"].values(), key=lambda r: (r["per_kg"] is None, r["per_kg"] or 0.0)
        )
        unit_rows = sorted(acc["unit"].values(), key=lambda r: r["price"])
        best = kg_rows[0] if kg_rows else None
        identities.append(
            {
                **base,
                "has_kg": bool(kg_rows),
                "best": best,
                "cheapest": (
                    {
                        "price": best["per_kg"],
                        "label": best["label"],
                        "store": best["store"],
                        "sample": best["sample"],
                        "presentation": best["presentation"],
                    }
                    if best
                    else None
                ),
                "retailers": kg_rows,
                "unit_only": unit_rows,
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[int, float]:
        best = item["best"]
        if best is None:
            return (2, float("inf"))
        value = best["per_pkg"] if item["is_package"] else best["per_kg"]
        return (0 if not item["is_package"] else 1, value or float("inf"))

    identities.sort(key=_sort_key)
    return identities, unmodeled


def produce_price_rows(db: Any, department: str = "Hortifruti") -> dict[str, Any]:
    """Price rows grouped by canonical produce identity for a department."""
    cache_key = f"{department}|produce"
    if _CACHE["key"] != cache_key or _CACHE["payload"] is None or time.time() - _CACHE["ts"] > _TTL:
        payload = _compute(db, department)
        _CACHE["key"] = cache_key
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
    return _CACHE["payload"]


def warm_produce_prices(department: str = "Hortifruti") -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        produce_price_rows(db, department)


def _compute(db: Any, department: str) -> dict[str, Any]:
    accepts = db.execute(
        select(LlmClassification.source_product_id).where(
            LlmClassification.department == department,
            LlmClassification.decision == "accept",
        )
    ).all()
    pids = {int(row[0]) for row in accepts}
    if not pids:
        return {
            "department": department,
            "identities": [],
            "accepted_products": 0,
            "unmodeled": 0,
            "samples": 0,
        }

    entries: list[dict[str, Any]] = []
    for row in current_listings(db):
        pid = row[_IDX["pid"]]
        if pid not in pids:
            continue
        cents = row[_IDX["cents"]]
        if cents is None or cents <= 0:
            continue
        raw = row[_IDX["raw"]] or ""
        entries.append(
            {
                "pid": pid,
                "price": cents / 100.0,
                "raw": raw,
                "retailer": row[_IDX["retailer"]],
                "retailer_name": row[_IDX["retailer_name"]] or "",
                "store": row[_IDX["store"]] or "",
            }
        )

    identities, unmodeled = _aggregate(entries)
    return {
        "department": department,
        "identities": identities,
        "accepted_products": len(pids),
        "unmodeled": unmodeled,
        "samples": len(entries),
    }
