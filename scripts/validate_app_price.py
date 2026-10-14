"""Validate in-store prices in the app's own API for a branch + product.

  python scripts/validate_app_price.py [storeId] [termo]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402
from find_product import products_from  # noqa: E402

BACKOFFICE = "/mobile/ofertas-backoffice/v1"
DEFAULT_TERMS = ["toscana", "nabrasa", "perdigao", "linguiça toscana nabrasa perdigao"]


def search(api: MeuAtacadaoAppApi, store: int, term: str) -> dict[object, dict]:
    payload = api.get_json(
        f"{BACKOFFICE}/produto/busca",
        {
            "pageNumber": 1,
            "pageSize": 10,
            "onlyWithOffer": "false",
            "filialId": store,
            "idFilial": store,
            "search": term,
        },
    )
    return {item.get("idSku"): item for item in products_from(payload)}


def main() -> None:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    terms = [sys.argv[2]] if len(sys.argv) > 2 else DEFAULT_TERMS

    api = MeuAtacadaoAppApi()
    api.authenticate()
    store_info = api.stores_by_cep("13184668")
    first = (store_info.get("data") or [{}])[0]
    print(
        f"loja {store} = {first.get('storeName')} | {first.get('address')}, {first.get('number')} "
        f"- {first.get('neighborhood')}, {first.get('city')}/{first.get('state')} | CEP {first.get('zipCode')}"
    )

    seen: dict[object, dict] = {}
    for term in terms:
        try:
            found = search(api, store, term)
        except AppApiError as exc:
            print(f"  busca '{term}' falhou: {exc}")
            continue
        print(f"  busca '{term}': {len(found)} produtos")
        seen.update(found)

    print(f"\ntotal unico: {len(seen)}")
    print("\n=== produtos Perdigão / Nabrasa / Toscana ===")
    hits = 0
    for item in seen.values():
        title = str(item.get("title", ""))
        if any(key in title.lower() for key in ("perdig", "nabrasa", "toscana")):
            hits += 1
            print(
                f"  {title}\n"
                f"      preco(varejo/atacado)={item.get('preco')} | finalPrice(oferta app)={item.get('finalPrice')} "
                f"| finalCardPrice(app+cartao)={item.get('finalCardPrice')} "
                f"| desconto={item.get('discountPercentage')}% | ean={item.get('ean')} | sku={item.get('idSku')} "
                f"| validade={item.get('validity')}"
            )
    if not hits:
        print("  nada encontrado. Titulos retornados:")
        for item in list(seen.values())[:25]:
            print("   -", item.get("title"))


if __name__ == "__main__":
    main()
