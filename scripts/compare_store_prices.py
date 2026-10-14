"""Compare the same product's price across the catalogs of several stores.

Reads catalog JSON artifacts produced by the collectors
(``write_catalog`` → ``<prefix>-catalog.json``) and reports, per product id,
whether the price is identical or divergent between stores. Use it as evidence
that a collector is really scoped per store, and to spot items whose price
differs between branches.

Usage
-----
    python scripts/compare_store_prices.py "artifacts/spani-catalog/*.json"
    python scripts/compare_store_prices.py "artifacts/atacadao-catalog/*.json" --top 15
    python scripts/compare_store_prices.py "artifacts/*-catalog/*.json" --only-divergent
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    store = payload.get("store") or {}
    label = store.get("name") or payload.get("retailer") or path.stem
    # Atmosphere sources identify the branch by `filial`, VIPCommerce ones by the
    # distribution centre; show whichever is present so the columns are readable.
    unit_parts = []
    if store.get("filial"):
        unit_parts.append(f"filial {store['filial']}")
    if store.get("centro_distribuicao"):
        unit_parts.append(f"cd {store['centro_distribuicao']}")
    return {
        "path": path,
        "label": f"{label} [{', '.join(unit_parts) or '-'}]",
        "products": {str(item["id"]): item for item in payload.get("products") or []},
    }


def money(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}".replace(".", ",")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="glob dos catálogos (ex.: 'artifacts/*-catalog/*.json')")
    parser.add_argument("--top", type=int, default=10, help="quantos produtos divergentes listar")
    parser.add_argument("--only-divergent", action="store_true", help="não imprime o resumo igual")
    args = parser.parse_args()

    paths = sorted(Path(p) for p in glob.glob(args.pattern))
    catalogs = [load(path) for path in paths if path.is_file()]
    if len(catalogs) < 2:
        raise SystemExit(f"preciso de pelo menos 2 catálogos, encontrei {len(catalogs)}")

    print(f"{len(catalogs)} catálogo(s):")
    for catalog in catalogs:
        print(f"  {catalog['label']:<44} {len(catalog['products']):>6} SKUs  ({catalog['path'].name})")

    common = set.intersection(*(set(catalog["products"]) for catalog in catalogs))
    print(f"\ninterseção por id de produto: {len(common)} SKUs presentes em todos")
    if not common:
        print(
            "nada em comum — normalmente significa que os catálogos são de runs/fontes "
            "diferentes (ex.: artefatos antigos da era VTEX ao lado dos novos da API do app)."
        )
        return

    identical = 0
    divergent: list[tuple[str, str, list[str]]] = []
    for product_id in sorted(common):
        prices = [catalog["products"][product_id].get("sales_price") for catalog in catalogs]
        normalized = {None if price is None else round(float(price), 2) for price in prices}
        if len(normalized) <= 1:
            identical += 1
        else:
            name = catalogs[0]["products"][product_id].get("name") or product_id
            divergent.append((product_id, name, [money(price) for price in prices]))

    if not args.only_divergent:
        print(f"mesmo preço em todas as lojas: {identical} ({identical / len(common):.1%})")
    print(f"preço divergente entre lojas:  {len(divergent)} ({len(divergent) / len(common):.1%})")

    if divergent:
        print(f"\n=== {min(args.top, len(divergent))} divergências ===")
        header = "  ".join(f"{catalog['label'][:18]:>18}" for catalog in catalogs)
        print(f"  {'produto':<46} {header}")
        for _, name, prices in divergent[: args.top]:
            cells = "  ".join(f"{price:>18}" for price in prices)
            print(f"  {name[:44]:<46} {cells}")


if __name__ == "__main__":
    main()
