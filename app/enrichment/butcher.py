"""Açougue comparison: group current listings into comparable cuts (R$/kg)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings
from app.db.models_v2 import LlmClassification
from app.enrichment.resolver import MeatItem

# tuple indexes of current_listings row
_IDX = {
    "effective_cents": 2,
    "product_id": 7,
    "raw_name": 9,
    "retailer": 14,
    "store": 15,
}

_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None, "use_llm": True}


def _llm_index(db: Session) -> dict[int, dict[str, Any]]:
    """product_id -> {decision, category} using online LLM verdicts.

    ``accept`` wins over ``reject``; among accepts the latest category is kept.
    """
    rows = db.execute(
        select(
            LlmClassification.source_product_id,
            LlmClassification.line_key,
            LlmClassification.decision,
            LlmClassification.created_at,
        ).order_by(LlmClassification.created_at)
    ).all()
    index: dict[int, dict[str, Any]] = {}
    for pid, line_key, decision, created_at in rows:
        category = None if line_key in ("reject", "NAO_CARNE") else line_key
        current = index.get(pid)
        candidate = {"decision": decision, "category": category, "_at": created_at}
        if current is None:
            index[pid] = candidate
            continue
        if decision == "accept" and (
            current["decision"] != "accept"
            or (
                candidate["_at"] is not None
                and current["_at"] is not None
                and candidate["_at"] > current["_at"]
            )
        ):
            index[pid] = candidate
    for verdict in index.values():
        verdict.pop("_at", None)
    return index


_FORM_DISPLAY = {
    "moida": "Moída",
    "peca_kg": "Peça / Kg",
    "fatiado": "Fatiado",
    "cubos": "Cubos",
    "desfiado": "Desfiado",
    "posta": "Posta",
}

_FORM_ORDER = {"moida": 0, "peca_kg": 1, "fatiado": 2, "cubos": 3, "desfiado": 4, "posta": 5}


def coarse_form(parsed: Any) -> str:
    """Map a parsed item to the coarse sale-form used to compare R$/kg.

    - Moída agregada (todo corte moído numa linha só);
    - Peça/Inteiro/Sem apresentação => "Peça / Kg" (o que se compara no fim é o kg);
    - Fatiado / Cubos / Desfiado / Posta permanecem formas próprias.
    """
    presentation = parsed.presentation
    if presentation == "moida" or parsed.cut in ("carne_moida",):
        return "moida"
    if presentation in ("fatiado", "cubos", "desfiado", "posta"):
        return presentation
    return "peca_kg"


def _compute(db: Session, use_llm: bool) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    llm = _llm_index(db) if use_llm else {}
    have_llm = bool(llm)

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
        if not item.parsed.is_meat:
            continue
        if have_llm:
            verdict = llm.get(item.product_id)
            if verdict is None or verdict["decision"] != "accept":
                continue
        items.append(item)

    # group by (category, coarse sale-form) -> comparable R$/kg rows
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        parsed = item.parsed
        form = coarse_form(parsed)
        if form == "moida":
            category = "Carne Moída"
        elif have_llm and (llm.get(item.product_id) or {}).get("category"):
            category = (llm.get(item.product_id) or {})["category"]
        else:
            category = parsed.label or parsed.raw_name
        key = (category, form)
        row = rows.setdefault(
            key,
            {
                "label": _FORM_DISPLAY[form],
                "category": category,
                "form": form,
                "conservation": parsed.conservation,
                "llm_category": category,
                "sources": {},
                "item_count": 0,
            },
        )
        row["item_count"] += 1
        price_kg = item.price_kg
        if price_kg is None:
            continue
        entry = row["sources"].setdefault(item.retailer, {"price_kg": None, "sample": None})
        if entry["price_kg"] is None or price_kg < entry["price_kg"]:
            entry["price_kg"] = price_kg
            entry["sample"] = item.raw_name

    groups = list(rows.values())
    groups = [g for g in groups if any(s["price_kg"] is not None for s in g["sources"].values())]
    groups.sort(
        key=lambda g: (
            (g["category"] or "").lower(),
            _FORM_ORDER.get(g["form"], 99),
            -g["item_count"],
        )
    )
    return len(items), groups, {"llm_active": have_llm, "accepted_products": len(llm)}


def butcher_comparison(
    db: Session, limit: int = 300, use_llm: bool = True
) -> dict[str, Any]:
    """Price rows per (category, sale-form) with R$/kg per source (TTL cached).

    When ``use_llm`` and online classifications exist, only products accepted by
    the LLM are considered and each row carries its ``llm_category``.
    """
    if (
        _CACHE["payload"] is None
        or time.time() - _CACHE["ts"] > 60
        or _CACHE["use_llm"] != use_llm
    ):
        items, groups, info = _compute(db, use_llm)
        _CACHE["payload"] = {"items": items, "groups": groups, "info": info}
        _CACHE["use_llm"] = use_llm
        _CACHE["ts"] = time.time()
    payload = _CACHE["payload"]
    return {
        "total_items": payload["items"],
        "total_groups": len(payload["groups"]),
        "llm": payload["info"],
        "groups": payload["groups"][:limit],
    }
