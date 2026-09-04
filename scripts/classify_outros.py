"""Classify the "Outros" pool (products without a clear department).

These items never matched any department in the deterministic taxonomy. We ask
DeepSeek to decide, for each product, its department (from the canonical list)
and a short canonical category, then persist the verdict with that department —
so "Outros" products are recovered into real departments (or stay grouped under
"Outros" when the model cannot tell).

Reply format: {"items": {"<id>": {"department": "...", "category": "..."}}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.catalog.taxonomy import CANONICAL_DEPARTMENTS
from app.classification.candidates import collect_department_candidates
from app.classification.deepseek import DeepSeekClient
from app.classification.store import upsert_decisions
from app.db.models_v2 import LlmClassification
from app.db.session import SessionLocal

_DEPT_KEYS = {re.sub(r"[^a-z0-9]+", "", d.casefold()): d for d in CANONICAL_DEPARTMENTS}


def _normalize_department(raw: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", (raw or "").casefold())
    return _DEPT_KEYS.get(key, "Outros")


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "outros"


def main() -> None:
    parser = argparse.ArgumentParser(description="Descobre departamento dos itens 'Outros'")
    parser.add_argument("--batch-size", type=int, default=120)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with SessionLocal() as db:
        candidates = collect_department_candidates(db, "Outros", exclude_accepted=True)
    if args.max_items:
        candidates = candidates[: args.max_items]
    if not candidates:
        print("Nenhum candidato em 'Outros'.")
        return

    batches = [
        candidates[i : i + args.batch_size]
        for i in range(0, len(candidates), args.batch_size)
    ]
    print(
        f"Outros — {len(candidates)} candidatos em {len(batches)} lote(s) "
        f"(~{sum(_est_tokens(c['raw_name']) for c in candidates)} tok)."
    )
    out_path = args.out or f"/data/llm_outros_{time.strftime('%Y%m%d_%H%M%S')}.json"
    client = DeepSeekClient()
    if args.dry_run or not client.ready:
        print("SEM chamada à API (dry-run ou chave ausente).")
        with open(out_path, "w", encoding="utf-8") as stream:
            json.dump({"department": "Outros", "candidates": candidates}, stream,
                      ensure_ascii=False, indent=2)
        print("Candidatos gravados em", out_path)
        return

    dept_list = "\n".join(f"- {d}" for d in CANONICAL_DEPARTMENTS)
    system = (
        "Você é um especialista em classificação de produtos de supermercado. "
        "Você recebe itens reais com IDs que não foram classificados em nenhum "
        "departamento. Para cada item diga o DEPARTAMENTO (um, exato, da lista "
        "fornecida) e uma CATEGORIA canônica curta (o tipo do produto, sem "
        "marca/peso/sabor). Regras:\n"
        "1) Escolha o departamento que melhor descreve o produto pela descrição/nome.\n"
        "2) Seja consistente: mesmo produto = mesmo departamento e mesma categoria.\n"
        "3) Não invente ids. Responda apenas com um objeto JSON válido no formato "
        '{"items": {"<id>": {"department": "...", "category": "..."}}} — sem notas '
        "nem texto fora do JSON.\n"
        "4) Se o produto for genérico demais para decidir, use department 'Outros' "
        "e category 'Outros'."
    )

    with SessionLocal() as db:
        accepted_elsewhere = set(
            db.scalars(
                select(LlmClassification.source_product_id).where(
                    LlmClassification.decision == "accept"
                )
            ).all()
        )

    rows: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    failed_batches: list[int] = []
    batch_id = str(uuid.uuid4())
    total_tokens = 0
    start = time.perf_counter()

    for index, batch in enumerate(batches, start=1):
        items = [(c["product_id"], c["raw_name"]) for c in batch]
        lines = [f"{pid} — {name}" for pid, name in items]
        user = (
            "DEPARTAMENTOS VÁLIDOS:\n" + dept_list + "\n\n"
            "Lista de itens (ID — nome):\n" + "\n".join(lines) +
            '\n\nResponda APENAS com o JSON no formato exato {"items": {"<id>": '
            '{"department": "...", "category": "..."}}}.'
        )
        parsed: dict[int, tuple[str, str]] | None = None
        last_error = ""
        for attempt in range(1, 4):
            content = client.chat_json(system, user)
            total_tokens += _est_tokens(user) + _est_tokens(content)
            try:
                payload = json.loads(content)
                raw = payload.get("items") or {}
                if not isinstance(raw, dict):
                    raise ValueError("sem items")
                parsed = {}
                for key, value in raw.items():
                    try:
                        pid = int(key)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(value, dict):
                        dept = _normalize_department(str(value.get("department") or ""))
                        cat = str(value.get("category") or "").strip() or "Outros"
                    elif isinstance(value, str):
                        parts = value.split("|", 1)
                        dept = _normalize_department(parts[0])
                        cat = (parts[1].strip() if len(parts) > 1 else "") or "Outros"
                    else:
                        dept, cat = "Outros", "Outros"
                    parsed[pid] = (dept, cat)
                break
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                if attempt < 3:
                    user += (
                        "\n\nA resposta anterior não pôde ser lida como JSON válido. "
                        'Responda novamente APENAS com o formato exato {"items": '
                        '{"<id>": {"department": "...", "category": "..."}}}.'
                    )
        if parsed is None:
            failed_batches.append(index)
            print(f"  lote {index}/{len(batches)}: FALHOU ({last_error[:80]})")
            continue

        batch_rows: list[dict[str, Any]] = []
        for cand in batch:
            pid = cand["product_id"]
            if pid in accepted_elsewhere:
                continue
            dept, cat = parsed.get(pid, ("Outros", "Outros"))
            accepted.append(
                {"product_id": pid, "raw_name": cand["raw_name"],
                 "retailer": cand["retailer"], "department": dept, "category": cat}
            )
            batch_rows.append(
                {
                    "source_product_id": pid,
                    "department": dept,
                    "line_key": cat[:80],
                    "retailer_slug": cand["retailer"],
                    "decision": "accept",
                    "model": client.model,
                    "batch_id": batch_id,
                    "prompt_version": "outros-1",
                }
            )
            rows.append(batch_rows[-1])
        if args.persist and batch_rows:
            with SessionLocal() as db:
                upsert_decisions(db, batch_rows)
        print(f"  lote {index}/{len(batches)}: {len(batch)} itens ok")

    elapsed = round(time.perf_counter() - start, 1)
    dept_counter = Counter(r["department"] for r in accepted)
    print(f"\nResultado: {len(accepted)} classificados | ~{total_tokens} tok | {elapsed}s")
    if failed_batches:
        print("AVISO lotes falhos:", failed_batches)
    print("Por departamento:", dict(dept_counter.most_common()))

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "department": "Outros",
        "model": client.model,
        "processed": len(rows),
        "failed_batches": failed_batches,
        "by_department": dict(dept_counter.most_common()),
        "items": accepted,
    }
    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    print("Gravado em", out_path)
    print("Amostra:", [(r["department"], r["category"], r["raw_name"][:50])
                       for r in accepted[:12]])


if __name__ == "__main__":
    sys.exit(main())
