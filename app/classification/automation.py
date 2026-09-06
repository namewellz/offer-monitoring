"""Automatic incremental classification of NEW products with the online LLM.

Runs after a catalog collection: products that have never been classified
(no row in ``llm_classifications``) are grouped by their deterministic store
department (``canonical_department``) and sent to DeepSeek in small batches to
get an accept/reject + canonical category — exactly like
``scripts/classify_department.py``, but as a server-side library so it can be
scheduled/triggered automatically.

Products whose deterministic department is unknown ("Outros") are NOT sent here
(they need the department-discovery runner) and are reported so an operator can
decide.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.catalog.v2.read import current_listings
from app.classification.canonical import (
    department_code,
    prompt_canonical_names,
    reject_token,
)
from app.classification.deepseek import DeepSeekClient, DeepSeekError, parse_categories
from app.classification.prompts import (
    build_department_prompt,
    department_system_prompt,
)
from app.classification.store import upsert_decisions
from app.db.models_v2 import LlmClassification
from app.db.session import SessionLocal

_IDX = {"cents": 2, "pid": 7, "raw": 9, "raw_categories": 12, "retailer": 14}

# departments that need the discovery runner (unknown deterministic dept)
_SKIP = {"Outros", None, ""}

DEFAULT_MAX_ITEMS = 800
BATCH_SIZE = 120


def new_product_candidates(
    db: Session,
    retailer: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Priced products that have never been classified (no row at all)."""
    seen = set(db.scalars(select(LlmClassification.source_product_id)).all())
    by_pid: dict[int, dict[str, Any]] = {}
    for row in current_listings(db):
        cents = row[_IDX["cents"]]
        if cents is None or cents <= 0:
            continue
        pid = row[_IDX["pid"]]
        if pid in seen:
            continue
        retailer_slug = row[_IDX["retailer"]]
        if retailer is not None and retailer_slug != retailer:
            continue
        raw_name = row[_IDX["raw"]] or ""
        entry = by_pid.get(pid)
        if entry is None:
            by_pid[pid] = {
                "product_id": pid,
                "raw_name": raw_name,
                "retailer": retailer_slug,
                "raw_categories": row[_IDX["raw_categories"]] or [],
            }
        elif len(raw_name) > len(entry["raw_name"]):
            entry["raw_name"] = raw_name
    ordered = sorted(by_pid.values(), key=lambda p: (p["retailer"], p["raw_name"]))
    return ordered[:limit] if limit else ordered


def bucket_by_department(candidates: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Split candidates by deterministic department (pure, testable)."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        raw_categories = cand.get("raw_categories") or []
        if isinstance(raw_categories, str):
            raw_categories = [raw_categories] if raw_categories else []
        else:
            raw_categories = list(raw_categories or [])
        department = canonical_department(raw_categories, cand.get("raw_name") or "")
        if department in _SKIP:
            department = "Outros"
        buckets.setdefault(department, []).append(cand)
    return buckets


def classify_new_products(
    db: Session,
    retailer: str | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    dry: bool = False,
) -> dict[str, Any]:
    """Classify never-classified priced products across known departments."""
    candidates = new_product_candidates(db, retailer=retailer, limit=max_items)
    if not candidates:
        return {"new": 0, "grouped": {}, "classified": [], "skipped_outros": 0}

    buckets = bucket_by_department(candidates)
    client = DeepSeekClient()
    ready = client.ready and not dry
    report: dict[str, Any] = {
        "new": len(candidates),
        "grouped": {dept: len(items) for dept, items in buckets.items()},
        "classified": [],
        "skipped_outros": len(buckets.get("Outros", [])),
    }

    for department, items in buckets.items():
        if department == "Outros":
            continue
        if not ready:
            report["classified"].append(
                {
                    "department": department,
                    "candidates": len(items),
                    "accepted": 0,
                    "rejected": 0,
                    "skipped_no_key": not client.ready,
                }
            )
            continue
        dept_rows = _classify_department_batches(db, client, department, items, retailer)
        accepted = sum(1 for r in dept_rows if r["decision"] == "accept")
        report["classified"].append(
            {
                "department": department,
                "candidates": len(items),
                "accepted": accepted,
                "rejected": len(dept_rows) - accepted,
                "skipped_no_key": False,
            }
        )
    return report


def _classify_department_batches(
    db: Session,
    client: DeepSeekClient,
    department: str,
    items: list[dict[str, Any]],
    retailer: str | None,
) -> list[dict[str, Any]]:
    token = reject_token(department)
    code = department_code(department)
    canonical_names = prompt_canonical_names(db, department=department)
    system = department_system_prompt(department)
    batch_id = str(uuid4())
    reject_values = {token.lower(), "nao_carne", "reject"}
    all_rows: list[dict[str, Any]] = []

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        batch_items = [(c["product_id"], c["raw_name"]) for c in batch]
        user = build_department_prompt(
            department, batch_items, canonical=canonical_names, retailer_label=retailer
        )
        cats: dict[int, tuple[str, str]] | None = None
        for _attempt in range(1, 4):
            try:
                content = client.chat_json(system, user)
                cats = parse_categories(content)
                break
            except DeepSeekError:
                user = (
                    user + "\n\nA resposta anterior não pôde ser lida como JSON válido. "
                    "Responda novamente APENAS com o JSON no formato exato "
                    '{"items": {"<id>": "<categoria>"}}, sem notas nem texto extra.'
                )
        if cats is None:
            continue  # lote falhou; produtos ficam para a próxima rodada
        batch_rows: list[dict[str, Any]] = []
        for cand in batch:
            pid = cand["product_id"]
            category, note = cats.get(pid, (token, ""))
            is_dept = (category or "").strip().lower() not in reject_values
            if not is_dept:
                category = token
            batch_rows.append(
                {
                    "source_product_id": pid,
                    "department": department,
                    "line_key": category if is_dept else "reject",
                    "retailer_slug": cand["retailer"],
                    "decision": "accept" if is_dept else "reject",
                    "reason": note,
                    "model": client.model,
                    "batch_id": batch_id,
                    "prompt_version": f"{code}-auto-1",
                }
            )
        with SessionLocal() as session:
            upsert_decisions(session, batch_rows)
        all_rows.extend(batch_rows)
    return all_rows
