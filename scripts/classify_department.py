"""Classify one store department end-to-end with the online DeepSeek API.

Sends the whole priced pool of a department (deterministic taxonomy: source
categories + product name) through DeepSeek and asks for one canonical category
per item (or the department reject token). Products are sent with their
``source_product_id`` and verdicts are stored in ``llm_classifications`` with a
``department`` scope (one product = one department = one category).

Usage (inside the api container):
    docker compose exec -T api python -m scripts.classify_department \
        --department Mercearia --persist --out /data/llm_mercearia.json
    docker compose cp api:/data/llm_mercearia.json outputs/

Piloto de uma rede (antes de rodar tudo):
    docker compose exec -T api python -m scripts.classify_department \
        --department Mercearia --retailer atacadao --max-items 600 \
        --dry-run --out /data/pool_mercearia_atacadao.json

Requires DEEPSEEK_API_KEY in the environment/.env.
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

from app.classification.candidates import collect_department_candidates
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
from app.db.session import SessionLocal


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower().strip()).strip("-")
    return slug[:80] or "reject"


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classifica um departamento via DeepSeek")
    parser.add_argument("--department", default="Mercearia", help="departamento (taxonomia)")
    parser.add_argument("--retailer", default=None, help="filtrar por rede (slug)")
    parser.add_argument("--batch-size", type=int, default=120)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--exclude-accepted", action="store_true", default=True,
                        help="não reenvia produto já aceito em outro departamento")
    parser.add_argument("--no-exclude-accepted", dest="exclude_accepted",
                        action="store_false", help="envia mesmo produtos aceitos em outro dept")
    parser.add_argument("--dry-run", action="store_true", help="não chama a API")
    parser.add_argument("--persist", action="store_true", help="grava no banco")
    parser.add_argument("--out", default=None, help="caminho do JSON de saída")
    args = parser.parse_args()

    department = args.department
    token = reject_token(department)
    code = department_code(department)
    with SessionLocal() as db:
        candidates = collect_department_candidates(
            db,
            department,
            retailer=args.retailer,
            exclude_accepted=args.exclude_accepted,
        )
    if args.max_items:
        candidates = candidates[: args.max_items]
    if not candidates:
        print(f"Nenhum candidato para o departamento '{department}'.")
        return

    by_retailer = Counter(c["retailer"] for c in candidates)
    batches = [
        candidates[i : i + args.batch_size]
        for i in range(0, len(candidates), args.batch_size)
    ]
    est = sum(_est_tokens(c["raw_name"]) for c in candidates)
    print(
        f"{department} — {len(candidates)} candidatos em {len(batches)} lote(s) "
        f"(~{est} tok de entrada)."
    )
    print("Por rede:", dict(by_retailer))

    out_path = args.out or (
        f"/data/llm_{code}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    )
    client = DeepSeekClient()
    print(f"Modelo: {client.model} | chave: {'ok' if client.ready else 'FALTANDO'}")

    if args.dry_run or not client.ready:
        print("\nSEM chamada à API (dry-run ou chave ausente).")
        if not client.ready and not args.dry_run:
            print("Adicione DEEPSEEK_API_KEY no .env e reinicie o api.")
        with open(out_path, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "department": department,
                    "dry_run": True,
                    "candidates": candidates,
                    "batches": len(batches),
                },
                stream,
                ensure_ascii=False,
                indent=2,
            )
        print(f"Candidatos gravados em {out_path}.")
        return

    with SessionLocal() as db:
        canonical_names = prompt_canonical_names(db, department=department)
    print(
        f"Vocabulário canônico no prompt: {len(canonical_names)} categorias "
        f"(rejeição: {token})."
    )

    reject_values = {token.lower(), "nao_carne", "reject"}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    batch_id = str(uuid.uuid4())
    total_tokens = 0
    start = time.perf_counter()
    failed_batches: list[int] = []

    system = department_system_prompt(department)
    for index, batch in enumerate(batches, start=1):
        items = [(c["product_id"], c["raw_name"]) for c in batch]
        user = build_department_prompt(
            department, items, canonical=canonical_names, retailer_label=args.retailer
        )
        cats: dict[int, tuple[str, str]] | None = None
        last_error = ""
        for attempt in range(1, 4):
            content = client.chat_json(system, user)
            total_tokens += _est_tokens(user) + _est_tokens(content)
            try:
                cats = parse_categories(content)
                break
            except DeepSeekError as exc:
                last_error = str(exc)
                if attempt < 3:
                    user = (
                        user
                        + "\n\nA resposta anterior não pôde ser lida como JSON "
                        "válido. Responda novamente APENAS com o JSON no formato "
                        'exato {"items": {"<id>": "<categoria>"}}, sem notas nem '
                        "texto extra."
                    )
        if cats is None:
            failed_batches.append(index)
            print(
                f"  lote {index}/{len(batches)}: FALHOU (JSON inválido: {last_error[:90]})"
            )
            continue

        batch_rows: list[dict[str, Any]] = []
        for cand in batch:
            pid = cand["product_id"]
            category, note = cats.get(pid, (token, ""))
            is_dept = (category or "").strip().lower() not in reject_values
            if not is_dept:
                category = token
            record = {
                "product_id": pid,
                "raw_name": cand["raw_name"],
                "retailer": cand["retailer"],
                "category": category,
                "decision": "accept" if is_dept else "reject",
                "note": note,
            }
            (accepted if is_dept else rejected).append(record)
            row = {
                "source_product_id": pid,
                "department": department,
                "line_key": category if is_dept else "reject",
                "retailer_slug": cand["retailer"],
                "decision": "accept" if is_dept else "reject",
                "reason": note,
                "model": client.model,
                "batch_id": batch_id,
                "prompt_version": f"{code}-1",
            }
            batch_rows.append(row)
            rows.append(row)
        if args.persist:
            with SessionLocal() as db:
                upsert_decisions(db, batch_rows)
        batch_ok = sum(1 for r in batch_rows if r["decision"] == "accept")
        print(
            f"  lote {index}/{len(batches)}: {len(batch)} itens -> {batch_ok} aceitos"
        )

    elapsed = round(time.perf_counter() - start, 1)
    cat_counts = Counter(r["category"] for r in accepted)
    print(
        f"\nResultado: {len(accepted)} em {department} | {len(rejected)} fora do "
        f"departamento ({token}) | ~{total_tokens} tok | {elapsed}s"
    )
    if failed_batches:
        print(f"AVISO: {len(failed_batches)} lote(s) falharam: {failed_batches}")
    print("Top categorias:", cat_counts.most_common(15))

    if args.persist:
        print(f"Banco: {len(rows)} decisões gravadas (incremental por lote).")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "department": department,
        "model": client.model,
        "total_candidates": len(candidates),
        "processed": len(rows),
        "failed_batches": failed_batches,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "top_categories": cat_counts.most_common(50),
        "accepted": accepted,
        "rejected": rejected,
        "rejected_by_retailer": dict(Counter(r["retailer"] for r in rejected)),
        "dry_run": False,
    }
    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    print(f"Gravado em {out_path}")

    print("\nAmostra aceitos:")
    for rec in accepted[:15]:
        print("   ", rec["retailer"], "|", rec["category"], "|", rec["raw_name"])
    print(f"Amostra {token}:")
    for rec in rejected[:15]:
        print("   ", rec["retailer"], "|", rec["raw_name"])


if __name__ == "__main__":
    sys.exit(main())
