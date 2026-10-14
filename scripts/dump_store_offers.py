"""Dump every in-store offer of a branch and look for a product.

  python scripts/dump_store_offers.py 632 [termo]

Uses the app's own endpoint:
  GET /mobile/ofertas-backoffice/v1/vitrine/mobile/v2
      ?pageNumber&pageSize(<=10)&pageProductSize(<=10)&filialId&idFilial
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

OUT = Path(r"C:\Android\capture")


def main() -> None:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    term = (sys.argv[2] if len(sys.argv) > 2 else "lingui").lower()

    api = MeuAtacadaoAppApi()
    api.authenticate()
    print(f"token ok | loja {store} | termo '{term}'")

    showcases: list[dict] = []
    products: dict[int, dict] = {}
    page = 1
    while page <= 40:
        try:
            data = api.showcase(store, page=page, page_size=10, products=10)
        except AppApiError as exc:
            print(f"pagina {page}: {exc}")
            break
        vitrines = (data or {}).get("Vitrines") or []
        if not vitrines:
            break
        print(f"  pagina {page}: {len(vitrines)} vitrines")
        for vitrine in vitrines:
            showcases.append(
                {
                    "id": vitrine.get("idVitrine"),
                    "title": vitrine.get("title"),
                    "format": vitrine.get("format"),
                    "products": len(vitrine.get("products") or []),
                }
            )
            for product in vitrine.get("products") or []:
                products[int(product["idSku"])] = product
        page += 1

    print(f"\nvitrines: {len(showcases)} | produtos unicos: {len(products)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"store_{store}_offers.json").write_text(
        json.dumps({"showcases": showcases, "products": list(products.values())}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"salvo em {OUT / f'store_{store}_offers.json'}")

    print(f"\n=== produtos com '{term}' ===")
    found = 0
    for product in products.values():
        title = str(product.get("title") or "")
        if term in title.lower():
            found += 1
            print(
                f"  SKU {product['idSku']} | {title}\n"
                f"      preco {product.get('preco')} | finalPrice {product.get('finalPrice')} "
                f"| cartao {product.get('finalCardPrice')} | desconto {product.get('discountPercentage')}% "
                f"| ean {product.get('ean')} | categoria {product.get('category')} "
                f"| validade {product.get('validity')}"
            )
    if not found:
        print("  nenhum. Titulos disponiveis (amostra):")
        for product in list(products.values())[:40]:
            print("   -", product.get("title"))


if __name__ == "__main__":
    main()
