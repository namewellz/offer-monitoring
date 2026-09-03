"""Açougue classification review data (server-side).

Collects current listings once and groups the parsed meat items into families
(variant groups) exactly like ``scripts/export_butcher_review``, so the web
screen and the exported JSON stay consistent. Also counts items that the
deterministic parser excluded (non-meat convenience foods, prepared/formed
products, plant-based, bacon-as-flavour) so reviewers can see the impact.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings
from app.db.models_v2 import LlmClassification
from app.enrichment.meat import (
    _LINGUICA_TYPE_RULES,
    CUTS,
    SPECIES,
    ParsedMeat,
    ascii_slug,
    fold,
)
from app.enrichment.resolver import MeatItem

# tuple indexes of current_listings row (see app/catalog/v2/read.py)
_IDX = {"effective_cents": 2, "product_id": 7, "raw_name": 9, "retailer": 14, "store": 15}

_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}

# Meat reference words (cuts/species/types). Used only to decide whether an
# item the parser EXCLUDED is Açougue-relevant (mentions a cut/species/type)
# instead of being an ordinary product of another department.
_MEAT_WORD_SINGLE: set[str] = set()
_MEAT_WORD_MULTI: list[str] = []


def _init_meat_words() -> None:
    if _MEAT_WORD_SINGLE:
        return
    for _canonical, needles in (*CUTS, *_LINGUICA_TYPE_RULES):
        for needle in needles:
            words = needle.split()
            if len(words) == 1:
                _MEAT_WORD_SINGLE.add(needle)
            else:
                _MEAT_WORD_MULTI.append(needle)
    for _canonical, needles in SPECIES:
        for needle in needles:
            if len(needle.split()) == 1:
                _MEAT_WORD_SINGLE.add(needle)
            else:
                _MEAT_WORD_MULTI.append(needle)


def _mentions_meat(raw_name: str) -> bool:
    _init_meat_words()
    if _MEAT_WORD_SINGLE.intersection(ascii_slug(raw_name).split()):
        return True
    folded = fold(raw_name)
    return any(phrase in folded for phrase in _MEAT_WORD_MULTI)


def _attr_list(parsed: ParsedMeat) -> list[str]:
    attrs: list[str] = []
    if parsed.bone_state == "sem_osso":
        attrs.append("sem osso")
    elif parsed.bone_state == "com_osso":
        attrs.append("com osso")
    if parsed.skin_state == "com_pele":
        attrs.append("com pele")
    elif parsed.skin_state == "sem_pele":
        attrs.append("sem pele")
    if parsed.presentation:
        attrs.append(parsed.presentation)
    if parsed.conservation:
        attrs.append(parsed.conservation)
    if parsed.seasoned:
        attrs.append("temperado")
    return attrs


def _collect(db: Session) -> tuple[list[MeatItem], dict[str, int], dict[str, int], int]:
    """Meat items (kept) + excluded counts + other-department count + scanned."""
    items: list[MeatItem] = []
    excluded: dict[str, int] = defaultdict(int)
    other_depts = 0
    scanned = 0
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]]
        effective = row[_IDX["effective_cents"]]
        scanned += 1
        if effective is None or effective <= 0:
            continue
        item = MeatItem(
            retailer=row[_IDX["retailer"]],
            store=row[_IDX["store"]],
            product_id=row[_IDX["product_id"]],
            raw_name=raw_name,
            effective_price_cents=effective,
        )
        parsed = item.parsed
        if parsed.is_meat:
            items.append(item)
            continue
        # Only items that reference a cut/species/type are Açougue-relevant
        # when the parser excludes them (the rest belong to other departments).
        if not _mentions_meat(raw_name):
            other_depts += 1
            continue
        for flag in ("non_meat", "prepared", "plant_based", "bacon_flavor_or_ingredient"):
            if flag in parsed.flags:
                excluded[flag] += 1
                break
        else:
            if parsed.cut is not None and parsed.species is None:
                excluded["cut_sem_especie"] += 1
            else:
                excluded["sem_corte"] += 1
    return items, dict(excluded), other_depts, scanned


def _ordered_groups(items: list[MeatItem]) -> list[tuple[tuple[Any, ...], list[MeatItem]]]:
    groups: dict[tuple[Any, ...], list[MeatItem]] = defaultdict(list)
    for item in items:
        key = item.parsed.variant_key
        if key is not None:
            groups[key].append(item)
    return sorted(groups.items(), key=lambda kv: -len(kv[1]))


def build_review_payload(
    items: list[MeatItem],
    excluded: dict[str, int],
    other_depts: int,
    scanned: int,
) -> dict[str, Any]:
    """Families payload in the same shape as the exported review JSON."""
    families: list[dict[str, Any]] = []
    associations = 0
    for index, (_key, members) in enumerate(_ordered_groups(items), start=1):
        first = members[0].parsed
        prices = [m.price_kg for m in members if m.price_kg is not None]
        cheapest = min(prices) if prices else None
        sources = sorted({m.retailer for m in members})
        members_sorted = sorted(
            members, key=lambda m: (m.retailer, m.raw_name.casefold())
        )
        if len(sources) >= 2:
            associations += 1
        families.append(
            {
                "id": index,
                "label": first.label,
                "species": first.species,
                "cut": first.cut,
                "cut_type": first.cut_type,
                "attributes": _attr_list(first),
                "item_count": len(members),
                "sources": sources,
                "source_count": len(sources),
                "price_kg_min": float(min(prices)) if prices else None,
                "price_kg_max": float(max(prices)) if prices else None,
                "cheapest": float(cheapest) if cheapest is not None else None,
                "items": [
                    {
                        "source": m.retailer,
                        "store": m.store,
                        "price_kg": float(m.price_kg) if m.price_kg is not None else None,
                        "raw_name": m.raw_name,
                        "product_id": m.product_id,
                        "cheapest": m.price_kg == cheapest if m.price_kg is not None else False,
                    }
                    for m in members_sorted
                ],
            }
        )
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "scanned_listings": scanned,
        "total_items": len(items),
        "excluded": excluded,
        "excluded_total": sum(excluded.values()),
        "other_departments": other_depts,
        "total_families": len(families),
        "families_with_associations": associations,
        "families": families,
    }


def butcher_review(db: Session) -> dict[str, Any]:
    """Full review payload with a short TTL cache (mirrors butcher.py)."""
    if _CACHE["payload"] is None or time.time() - _CACHE["ts"] > 60:
        items, excluded, other_depts, scanned = _collect(db)
        payload = build_review_payload(items, excluded, other_depts, scanned)
        payload["llm"] = _llm_overlay(db, payload)
        _CACHE["payload"] = payload
        _CACHE["ts"] = time.time()
    return _CACHE["payload"]


def _llm_overlay(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach DeepSeek verdicts (llm_classifications) to each family item.

    For a product with several rows (per-line + Açougue run), ``accept`` wins and
    the latest category is kept, so the reviewer sees the LLM decision.
    """
    rows = db.execute(
        select(
            LlmClassification.source_product_id,
            LlmClassification.line_key,
            LlmClassification.decision,
            LlmClassification.reason,
            LlmClassification.created_at,
        ).order_by(LlmClassification.created_at)
    ).all()
    by_product: dict[int, dict[str, Any]] = {}
    for source_product_id, line_key, decision, reason, created_at in rows:
        candidate = {
            "decision": decision,
            "category": None if line_key in ("reject", "NAO_CARNE") else line_key,
            "reason": reason,
            "_at": created_at,
        }
        current = by_product.get(source_product_id)
        if current is None:
            by_product[source_product_id] = candidate
            continue
        if decision == "accept":
            if current["decision"] != "accept" or (
                candidate["_at"] is not None
                and current["_at"] is not None
                and candidate["_at"] > current["_at"]
            ):
                by_product[source_product_id] = candidate
        # a later "reject" does not override an existing "accept"
    for verdict in by_product.values():
        verdict.pop("_at", None)
    classified = accepted = rejected = 0
    for family in payload["families"]:
        llm_ok = 0
        for item in family["items"]:
            verdict = by_product.get(item["product_id"])
            if verdict is None:
                item["llm_decision"] = None
                item["llm_category"] = None
                continue
            item["llm_decision"] = verdict["decision"]
            item["llm_category"] = verdict["category"]
            classified += 1
            if verdict["decision"] == "accept":
                accepted += 1
                llm_ok += 1
            else:
                rejected += 1
        family["llm_ok_count"] = llm_ok
        family["llm_total_count"] = sum(
            1 for it in family["items"] if it.get("llm_decision") is not None
        )
    return {
        "classified_products": len(by_product),
        "classified_items": classified,
        "accepted": accepted,
        "rejected": rejected,
    }
