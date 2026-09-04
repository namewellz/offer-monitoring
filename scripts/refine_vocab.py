"""Generate a canonical PRODUCT vocabulary for a department from its real names.

The point: a canonical category should be the PRODUCT NAME without brand, weight,
quantity, unit or presentation (ex.: 'Maçã Fuji Kg' / 'Maçã Fuji 1kg' /
'Maçã Fuji Unidade' -> 'Maçã Fuji'). We send a representative sample of real
product names (the department pool) to DeepSeek and ask it to return the
canonical product list that covers them.

Usage (inside the api container):
    docker compose exec -T api python -m scripts.refine_vocab \
        --department Hortifruti --out /data/vocab_hortifruti.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter

from app.classification.candidates import collect_department_candidates
from app.classification.deepseek import DeepSeekClient
from app.db.session import SessionLocal

_STRIP_TAIL = re.compile(
    r"\s*(?:kg|quilos?|kilos?|g|gr|grs|gramas?|ml|l|lt|litros?|un|und|unid|"
    r"unidade|unidades|bandeja|pacote|saco|sach[eê]|pote|vidro|lata|caixa|"
    r"embalagem|c[oô]m\s*\d+\s*(?:un|unid|unidades)?|reserva|fardo|" +
    r"(?:\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|un|unid)))\s*$",
    re.IGNORECASE,
)


def _clean(label: str) -> str:
    label = re.sub(r"\s+", " ", (label or "").strip())
    while True:
        new = _STRIP_TAIL.sub("", label).strip()
        # remove trailing connector like "Maçã de" / "Maçã em"
        new = re.sub(r"\s+(em|de|da|do|com|e)\s*$", "", new).strip()
        if new == label:
            break
        label = new
    # remove brand-like markers sometimes left: uppercase lead words of size
    return label[:120] if label else ""


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera vocabulário canônico de produto por dept")
    parser.add_argument("--department", default="Hortifruti")
    parser.add_argument("--sample", type=int, default=1200)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with SessionLocal() as db:
        pool = collect_department_candidates(db, args.department)
    # deduplicate by normalized name and cap the sample (mix across retailers)
    seen = set()
    sample = []
    for cand in pool:
        name = re.sub(r"\s+", " ", (cand["raw_name"] or "").strip()).lower()
        key = re.sub(r"[^a-z0-9]+", "", name)
        if key in seen or not key:
            continue
        seen.add(key)
        sample.append(cand["raw_name"])
        if len(sample) >= args.sample:
            break
    if not sample:
        print("Sem nomes para", args.department)
        return
    print(f"{args.department}: {len(pool)} no pool; amostra {len(sample)} nomes.")

    out_path = args.out or (
        f"/data/vocab_{re.sub(r'[^a-z]+', '_', args.department.lower()).strip('_')}"
        f"_{time.strftime('%Y%m%d_%H%M%S')}.json"
    )
    client = DeepSeekClient()
    if not client.ready:
        print("Sem chave DeepSeek.")
        return

    system = (
        "Você é um especialista em organização do sortido de supermercado. "
        "Você recebe nomes REAIS de produtos de um departamento. Sua tarefa é "
        "gerar o VOCABULÁRIO CANÔNICO DE PRODUTO desse departamento: uma lista "
        "de nomes de produto (categoria canônica). Regras:\n"
        "1) Cada categoria é o NOME DO PRODUTO, SEM marca, sem peso/quantidade/"
        "unidade (kg, g, ml, L, un), sem apresentação (bandeja, pacote, saco, "
        "unidade de venda) e sem peso de reserva.\n"
        "2) Nomes que são o mesmo produto em apresentações diferentes devem "
        "virar UMA categoria (ex.: 'Maçã Fuji Kg', 'Maçã Fuji 1kg', 'Maçã Fuji "
        "Unidade' -> 'Maçã Fuji'; 'Banana Maçã Kg'/'Banana Maçã 1kg' -> 'Banana "
        "Maçã').\n"
        "3) Conserve a variedade quando for parte do produto (ex.: 'Maçã Fuji', "
        "'Maçã Gala', 'Banana Prata', 'Banana Nanica', 'Tomate Italiano', "
        "'Tomate Salada').\n"
        "4) Cubra toda a diversidade da lista, com nomes curtos e consistentes. "
        "Não crie sinônimos.\n"
        'Responda APENAS com um objeto JSON no formato {"categories": ["...", '
        '"..."]} — um array de strings, sem texto fora do JSON.'
    )

    lines = [f"- {name}" for name in sample]
    user = (
        f"DEPARTAMENTO: {args.department}\n\nNomes reais de produtos:\n"
        + "\n".join(lines)
        + '\n\nResponda APENAS com o JSON {"categories": [...]}.'
    )
    print(f"Enviando ~{_est_tokens(user)} tok …")
    content = client.chat_json(system, user)
    try:
        payload = json.loads(content)
        raw = payload.get("categories") or []
        if isinstance(raw, str):
            raw = [raw]
    except json.JSONDecodeError as exc:
        print("Falha ao ler JSON:", exc)
        print(content[:500])
        return

    categories: list[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        cleaned = _clean(value)
        if cleaned and cleaned not in categories:
            categories.append(cleaned)
    # order by frequency of names that contain each category (approx)
    cat_counter = Counter()
    folded_pool = [re.sub(r"[^a-z0-9]+", "", (n or "").lower()) for n in sample]
    for cat in categories:
        f = re.sub(r"[^a-z0-9]+", "", cat.lower())
        if not f:
            continue
        cat_counter[cat] = sum(1 for name in folded_pool if f in name)
    categories.sort(key=lambda c: (-cat_counter.get(c, 0), c))
    categories = categories[:400]

    with open(out_path, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "department": args.department,
                "model": client.model,
                "sample_names": len(sample),
                "categories": categories,
                "category_count": len(categories),
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Vocabulário com {len(categories)} categorias gravado em {out_path}")
    for cat in categories[:40]:
        print("  -", cat)


if __name__ == "__main__":
    sys.exit(main())
