"""Search a collected catalog artifact for a product and print its price tiers.

Use it to produce evidence for a specific item straight from the collector output
(no HTTP call involved).

Usage
-----
    python scripts/find_catalog_product.py artifacts/atacadao-catalog/*.json toscana nabrasa
    python scripts/find_catalog_product.py "artifacts/spani-catalog/*.json" arroz --limit 5
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def money(value) -> str:
    if value is None:
        return "—"
    return f"R$ {float(value):.2f}".replace(".", ",")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="glob dos catálogos")
    parser.add_argument("terms", nargs="+", help="todos os termos precisam aparecer no nome")
    parser.add_argument("--limit", type=int, default=8, help="máximo de itens por catálogo")
    args = parser.parse_args()

    terms = [term.casefold() for term in args.terms]
    found_any = False
    for name in sorted(glob.glob(args.pattern)):
        path = Path(name)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        store = payload.get("store") or {}
        label = (
            f"{store.get('name')} filial {store.get('filial')}"
            if store.get("filial")
            else f"{store.get('name')} cd {store.get('centro_distribuicao')}"
        )
        hits = [
            product
            for product in payload.get("products") or []
            if all(term in str(product.get("name") or "").casefold() for term in terms)
        ]
        if not hits:
            continue
        found_any = True
        print(f"\n=== {label}  ({path.name}) — {len(hits)} item(ns) ===")
        for product in hits[: args.limit]:
            tiers = ", ".join(
                f"{tier.get('condition')}={money(tier.get('price'))}"
                for tier in product.get("tier_prices") or []
            )
            print(
                f"  {str(product['id']):>10}  {str(product['name'])[:52]:<52} "
                f"regular={money(product.get('regular_price'))} "
                f"sales={money(product.get('sales_price'))} "
                f"oferta={tiers or '—'} disponivel={product.get('available')} ean={product.get('ean')}"
            )
    if not found_any:
        print("nenhum item encontrado em " + args.pattern)


if __name__ == "__main__":
    main()
