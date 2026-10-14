"""Constrói um dataset de resolução a partir das saídas de classificação.

Lê ``outputs/llm_*.json`` (campo ``accepted``) e gera um diretório com
``source_products.jsonl`` (produto bruto + label do pipeline atual) e
``expected_interpretations.jsonl`` (template de golden a ser revisado por
humano). Os demais arquivos do dataset (canonical_entities, candidate_sets,
expected_resolutions, pair_labels) são curados manualmente; este script
automatiza apenas a parte repetitiva da extração dos produtos reais.

Uso:
    python -m scripts.build_resolution_dataset \
        --out tests/fixtures/resolution/proposal \
        --departments Bebidas,Mercearia --limit-per-department 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Permite rodar como ``python scripts/build_resolution_dataset.py`` sem -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.identity.schemas import department_code_of_label  # noqa: E402


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").lower().strip()).strip("-")
    return value or "item"


def _parse_outputs(path: Path) -> list[dict]:
    """Lê um llm_*.json e devolve os itens ``accepted``."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    department = payload.get("department") or ""
    accepted = payload.get("accepted") or []
    out = []
    for item in accepted:
        out.append(
            {
                "external_id": str(item.get("product_id") or ""),
                "raw_name": item.get("raw_name") or "",
                "retailer": item.get("retailer") or "",
                "department": department,
                "category": item.get("category") or "",
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Constrói dataset de resolução a partir das saídas")
    parser.add_argument("--source-dir", default="outputs")
    parser.add_argument("--departments", default=None,
                        help="filtrar por rótulo de departamento (separado por vírgula)")
    parser.add_argument("--limit-per-department", type=int, default=None)
    parser.add_argument("--out", default="tests/fixtures/resolution/proposal")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    wanted = {d.strip() for d in (args.departments or "").split(",") if d.strip()}

    items: list[dict] = []
    for path in sorted(source_dir.glob("llm_*.json")):
        for item in _parse_outputs(path):
            if wanted and item["department"] not in wanted:
                continue
            items.append(item)

    if args.limit_per_department:
        seen: dict[str, int] = {}
        limited: list[dict] = []
        for item in items:
            dept = item["department"]
            if seen.get(dept, 0) >= args.limit_per_department:
                continue
            seen[dept] = seen.get(dept, 0) + 1
            limited.append(item)
        items = limited

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    products_path = out / "source_products.jsonl"
    interpretations_path = out / "expected_interpretations.jsonl"
    readme_path = out / "README.md"

    with products_path.open("w", encoding="utf-8") as products, \
            interpretations_path.open("w", encoding="utf-8") as interpretations:
        for index, item in enumerate(items, start=1):
            source_id = f"sp:{_slug(item['department'])}-{index:04d}"
            product = {
                "id": source_id,
                "external_id": item["external_id"],
                "source_id": item["retailer"],
                "retailer": item["retailer"],
                "raw_name": item["raw_name"],
                "raw_brand": None,
                "raw_categories": [item["department"]],
                "raw_gtin": None,
                "raw_measure": "UN",
                "raw_quantity": None,
                "raw_unit": None,
                "raw_package": None,
                "department": item["department"],
                "category": item["category"],
            }
            products.write(json.dumps(product, ensure_ascii=False) + "\n")

            interpretation = {
                "source_product_id": source_id,
                "department_code": department_code_of_label(item["department"]),
                "family_code": None,
                "product_type": item["category"],
                "brand": None,
                "net_quantity": None,
                "unit": None,
                "package_type": None,
                "variant": None,
                "flavor": None,
                "sale_mode": None,
                "max_level": None,
                "difficulty": None,
                "note": "REVISAR: identidade não curada (gerada automaticamente).",
            }
            interpretations.write(json.dumps(interpretation, ensure_ascii=False) + "\n")

    readme_path.write_text(
        "# Dataset de resolução — rascunho (não congelado)\n\n"
        "Gerado por `scripts/build_resolution_dataset.py` a partir de "
        "`outputs/llm_*.json`.\n\n"
        "Os campos de identidade de `expected_interpretations.jsonl` estão "
        "marcados como `REVISAR`: é necessária curadoria humana antes de "
        "congelar como dataset dourado.\n\n"
        "Arquivos ainda ausentes (curados manualmente):\n"
        "- `canonical_entities.jsonl`\n"
        "- `candidate_sets.jsonl`\n"
        "- `expected_resolutions.jsonl`\n"
        "- `pair_labels.jsonl`\n",
        encoding="utf-8",
    )

    print(f"{len(items)} itens gravados em {out}")
    print(f"  {products_path.name}")
    print(f"  {interpretations_path.name}")
    print(f"  {readme_path.name}")


if __name__ == "__main__":
    sys.exit(main())
