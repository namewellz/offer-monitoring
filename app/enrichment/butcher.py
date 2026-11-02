"""Açougue comparison: group current listings into comparable cuts (R$/kg)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings, is_price_fresh
from app.stores import CURRENT_FILTER
from app.classification.canonical import (
    canonical_map,
    equivalent_cut_category,
    seed_categories,
)
from app.db.models_v2 import LlmClassification
from app.enrichment.meat import plain_coxa_sobrecoxa
from app.enrichment.resolver import MeatItem

# tuple indexes of current_listings row
_IDX = {
    "effective_cents": 2,
    "confirmed": 5,
    "product_id": 7,
    "raw_name": 9,
    "retailer": 14,
    "store": 15,
    "basis": 16,
}

log = logging.getLogger(__name__)

# Cache por (filtro de loja, use_llm): um ``?rede=`` ou ``?all=1`` não despeja o
# padrão. Cada entrada: {"ts", "payload"}.
_CACHE: dict[tuple[str, bool], dict[str, Any]] = {}
_MAX_ENTRIES = 16
# Single-flight: só um recálculo por vez (a VM tem 2 CPUs); quem chega depois
# espera e reaproveita o resultado em vez de recalcular em paralelo.
_LOCK = threading.Lock()
_REFRESHING: set[tuple[str, bool]] = set()
_STATE_LOCK = threading.Lock()

# Preços trocam a cada coleta agendada; 5min evita recálculo de ~13s a cada
# requisição isolada sem sacrificar frescor (o warm-up mantém quente).
_TTL = 300


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


def _compute(
    db: Session,
    use_llm: bool,
    rows: Sequence[tuple[Any, ...]] | None = None,
    release: bool = False,
) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    """Compute the comparison.

    ``rows`` may be a pre-fetched ``current_listings(fresh_only=True,
    accepted_only=True)`` result; it is only used when LLM verdicts are active,
    because then non-accepted and stale rows are discarded below anyway. Without
    verdicts every listing counts, so the rows are fetched here unfiltered by
    acceptance. ``release`` ends the transaction once the DB reads are done
    (only for sessions owned by the caller).
    """
    llm = _llm_index(db) if use_llm else {}
    have_llm = bool(llm)
    canonical: dict[str, str] = {}
    if have_llm:
        seed_categories(db)
        canonical = canonical_map(db)
    if rows is None or not have_llm:
        # fresh_only/accepted_only só pré-filtram no SQL o que o laço abaixo já
        # descarta (preço velho; produto sem accept quando há veredictos).
        rows = current_listings(
            db, fresh_only=True, accepted_only=have_llm, release=True
        )
    if release:
        db.rollback()

    items: list[MeatItem] = []
    for row in rows:
        raw_name = row[_IDX["raw_name"]]
        effective = row[_IDX["effective_cents"]]
        if effective is None or effective <= 0:
            continue
        # Preço só vale se foi re-confirmado há no máximo 2 dias.
        if not is_price_fresh(row[_IDX["confirmed"]]):
            continue
        item = MeatItem(
            retailer=row[_IDX["retailer"]],
            store=row[_IDX["store"]],
            product_id=row[_IDX["product_id"]],
            raw_name=raw_name,
            effective_price_cents=effective,
            price_basis_unit=row[_IDX["basis"]],
        )
        if not item.parsed.is_meat:
            continue
        # Empanado e a passarinho não são a peça de coxa/sobrecoxa. Se entrarem
        # na mesma linha, o mais barato deles esconde a peça (ex.: Dalben 1kg).
        if not plain_coxa_sobrecoxa(item.parsed, item.raw_name):
            continue
        if have_llm:
            verdict = llm.get(item.product_id)
            if verdict is None or verdict["decision"] != "accept":
                continue
        items.append(item)

    # group by (canonical category, coarse sale-form) -> comparable R$/kg rows
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        parsed = item.parsed
        form = coarse_form(parsed)
        if form == "moida":
            category = "Carne Moída"
        elif have_llm and (llm.get(item.product_id) or {}).get("category"):
            raw = (llm.get(item.product_id) or {})["category"]
            category = equivalent_cut_category(canonical.get(raw, raw) or raw)
        else:
            category = equivalent_cut_category(parsed.label or parsed.raw_name)
        key = (category, form)
        row = rows.setdefault(
            key,
            {
                "department": "Açougue",
                "unit": "kg",
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
        entry = row["sources"].setdefault(
            item.retailer, {"price_kg": None, "sample": None, "store": None}
        )
        if entry["price_kg"] is None or price_kg < entry["price_kg"]:
            entry["price_kg"] = price_kg
            entry["sample"] = item.raw_name
            entry["store"] = item.store

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


def _cache_key(use_llm: bool) -> tuple[str, bool]:
    return (CURRENT_FILTER.get().key, use_llm)


def _is_fresh(entry: dict[str, Any] | None) -> bool:
    return entry is not None and time.time() - entry["ts"] <= _TTL


def _store(key: tuple[str, bool], payload: dict[str, Any]) -> dict[str, Any]:
    entry = {"ts": time.time(), "payload": payload}
    _CACHE[key] = entry
    while len(_CACHE) > _MAX_ENTRIES:
        oldest = min(_CACHE, key=lambda k: _CACHE[k]["ts"])
        _CACHE.pop(oldest, None)
    return entry


def _refresh(
    use_llm: bool,
    db: Session | None = None,
    rows: Sequence[tuple[Any, ...]] | None = None,
    force: bool = False,
    release: bool = False,
) -> dict[str, Any]:
    """Recompute under the single-flight lock for the current store filter.

    With ``db=None`` a private session is opened (and its transaction released
    as soon as the reads finish). If another thread refreshed the same key while
    we waited for the lock, its fresh result is reused.
    """
    key = _cache_key(use_llm)
    with _LOCK:
        entry = _CACHE.get(key)
        if not force and _is_fresh(entry):
            return entry
        if db is None:
            from app.db.session import SessionLocal

            with SessionLocal() as own:
                items, groups, info = _compute(own, use_llm, rows=rows, release=True)
        else:
            items, groups, info = _compute(db, use_llm, rows=rows, release=release)
        return _store(key, {"items": items, "groups": groups, "info": info})


def _refresh_in_background(use_llm: bool) -> None:
    flt = CURRENT_FILTER.get()
    key = (flt.key, use_llm)
    with _STATE_LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

    def run() -> None:
        token = CURRENT_FILTER.set(flt)
        try:
            _refresh(use_llm)
        except Exception:  # noqa: BLE001 - nunca derruba a thread de fundo
            log.exception("butcher cache background refresh failed")
        finally:
            CURRENT_FILTER.reset(token)
            with _STATE_LOCK:
                _REFRESHING.discard(key)

    threading.Thread(target=run, daemon=True, name="butcher-refresh").start()


def butcher_comparison(
    db: Session,
    limit: int = 300,
    use_llm: bool = True,
    rows: Sequence[tuple[Any, ...]] | None = None,
    release: bool = False,
) -> dict[str, Any]:
    """Price rows per (category, sale-form) with R$/kg per source (TTL cached).

    When ``use_llm`` and online classifications exist, only products accepted by
    the LLM are considered and each row carries its ``llm_category``.

    Cache: fresh entry -> returned; stale entry -> returned immediately while a
    single background refresh recomputes it; no entry -> computed now (one at a
    time). When the caller passes pre-fetched ``rows`` a stale entry is
    recomputed synchronously from them (no extra query). ``release`` (only for
    sessions owned by the caller) ends the transaction after the DB reads.
    """
    key = _cache_key(use_llm)
    entry = _CACHE.get(key)
    if not _is_fresh(entry):
        if entry is not None and rows is None:
            _refresh_in_background(use_llm)
        else:
            entry = _refresh(use_llm, db=db, rows=rows, release=release)
    payload = entry["payload"]
    return {
        "total_items": payload["items"],
        "total_groups": len(payload["groups"]),
        "llm": payload["info"],
        "groups": payload["groups"][:limit],
    }


def warm_butcher_cache() -> None:
    """Recompute e atualiza o cache (usado por thread de warm-up da API)."""
    _refresh(use_llm=True)
