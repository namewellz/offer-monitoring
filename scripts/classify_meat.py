"""Classify a meat product line with the online DeepSeek API.

Collects candidate source products (by keyword) and asks DeepSeek, in batches,
which of them really are that product (e.g. Bacon) vs false positives that only
carry the word as flavour/ingredient. Products are sent with their
``source_product_id`` so the verdict can be related back to the DB.

Usage (inside the api container):
    docker compose exec -T api python -m scripts.classify_meat \
        --line bacon --persist --out /data/llm_bacon.json
    docker compose cp api:/data/llm_bacon.json outputs/

Dry-run (no API call; dumps candidates + batches to inspect first):
    docker compose exec -T api python -m scripts.classify_meat --line bacon --dry-run

Requires DEEPSEEK_API_KEY in the environment/.env.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections import Counter
from typing import Any

from app.classification.candidates import collect_candidates
from app.classification.deepseek import DeepSeekClient, parse_ids_json
from app.classification.prompts import MEAT_LINES, SYSTEM_PROMPT, build_user_prompt
from app.classification.store import upsert_decisions
from app.db.session import SessionLocal


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classifica linha de carne via DeepSeek")
    parser.add_argument("--line", default="bacon", choices=sorted(MEAT_LINES))
    parser.add_argument("--retailer", default=None, help="filtrar por rede (slug)")
    parser.add_argument("--batch-size", type=int, default=120)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="não chama a API")
    parser.add_argument("--persist", action="store_true", help="grava no banco")
    parser.add_argument("--out", default=None, help="caminho do JSON de saída")
    args = parser.parse_args()

    line = MEAT_LINES[args.line]

    with SessionLocal() as db:
        candidates = collect_candidates(db, line["keywords"], retailer=args.retailer)
    if args.max_items:
        candidates = candidates[: args.max_items]
    if not candidates:
        print("Nenhum candidato encontrado.")
        return

    by_retailer = Counter(c["retailer"] for c in candidates)
    batches = [
        candidates[i : i + args.batch_size]
        for i in range(0, len(candidates), args.batch_size)
    ]
    est_tok = sum(_est_tokens(c["raw_name"]) for c in candidates)
    print(
        f"Linha '{line['label']}' — {len(candidates)} candidatos em "
        f"{len(batches)} lote(s) (~{est_tok} tok de entrada)."
    )
    print("Por rede:", dict(by_retailer))

    out_path = args.out or (
        f"/data/llm_{args.line}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    )

    client = DeepSeekClient()
    print(f"Modelo configurado: {client.model} | chave: {'ok' if client.ready else 'FALTANDO'}")

    if args.dry_run or not client.ready:
        print("\nMODO: sem chamada à API.")
        if not client.ready and not args.dry_run:
            print("Adicione DEEPSEEK_API_KEY no .env para classificar de verdade.")
        # still dump the candidate list so the prompt payload can be inspected
        payload: dict[str, Any] = {
            "line": args.line,
            "label": line["label"],
            "dry_run": True,
            "candidates": candidates,
            "batches": len(batches),
        }
        with open(out_path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        print(f"Candidatos gravados em {out_path} (dry-run).")
        return

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    batch_id = str(uuid.uuid4())
    start = time.perf_counter()
    total_tokens = 0

    for index, batch in enumerate(batches, start=1):
        items = [(c["product_id"], c["raw_name"]) for c in batch]
        user_prompt = build_user_prompt(line, items)
        content = client.chat_json(SYSTEM_PROMPT, user_prompt)
        decisions, reasons = {}, {}
        try:
            decisions, reasons = parse_ids_json(content, {pid for pid, _ in items})
        except Exception as exc:  # noqa: BLE001 - single failed batch must not stop the run
            print(f"  lote {index}/{len(batches)}: JSON inválido ignorando fallback rejeitar -> {str(exc)[:80]}")
        total_tokens += _est_tokens(user_prompt) + _est_tokens(content)

        batch_rows: list[dict[str, Any]] = []
        for cand in batch:
            pid = cand["product_id"]
            decision = decisions.get(pid, "reject")
            reason = reasons.get(pid)
            record = {
                "product_id": pid,
                "raw_name": cand["raw_name"],
                "retailer": cand["retailer"],
                "reason": reason,
            }
            if decision == "accept":
                accepted.append(record)
            else:
                if not reason:
                    reason = "não parece Bacon/linha de verdade (sabor/ingrediente?)"
                rejected.append({**record, "reason": reason})
            row = {
                "source_product_id": pid,
                "line_key": args.line,
                "retailer_slug": cand["retailer"],
                "decision": decision,
                "reason": reason,
                "model": client.model,
                "batch_id": batch_id,
                "prompt_version": "1",
            }
            batch_rows.append(row)
            rows.append(row)
        if args.persist:
            with SessionLocal() as db:
                upsert_decisions(db, batch_rows)
        print(
            f"  lote {index}/{len(batches)}: {len(batch)} itens -> "
            f"{sum(1 for r in batch_rows if r['decision']=='accept')} aceitos"
        )

    elapsed = round(time.perf_counter() - start, 1)
    print(f"\nResultado: {len(accepted)} aceitos | {len(rejected)} rejeitados "
          f"| ~{total_tokens} tok | {elapsed}s")

    if args.persist:
        print(f"Banco: {len(rows)} decisões gravadas (incremental por lote).")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "line": args.line,
        "label": line["label"],
        "model": client.model,
        "total_candidates": len(candidates),
        "processed": len(rows),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted": accepted,
        "rejected": rejected,
        "rejected_by_retailer": dict(
            Counter(r["retailer"] for r in rejected)
        ),
        "dry_run": False,
    }
    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    print(f"Gravado em {out_path}")

    # quick peeks for human review
    print("\nAmostra de aceitos:")
    for rec in accepted[:12]:
        print("   ", rec["retailer"], "|", rec["raw_name"])
    print("Amostra de rejeitados:")
    for rec in rejected[:15]:
        print("   ", rec["retailer"], "|", rec["raw_name"], "->", (rec["reason"] or "")[:60])


if __name__ == "__main__":
    sys.exit(main())
