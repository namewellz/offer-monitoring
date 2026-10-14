"""Find a product in a branch's in-store offers and print its prices.

Endpoint discovered in the live app:
    GET /mobile/ofertas-backoffice/v1/produto/busca
        ?idCategoria&pageNumber&pageSize&onlyWithOffer&filialId&idFilial
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

BACKOFFICE = "/mobile/ofertas-backoffice/v1"
OUT = Path(r"C:\Android\capture")


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")
    else:
        yield path, node


def products_from(payload) -> list[dict]:
    """Collect every dict that looks like an offer (has title + price)."""
    out: list[dict] = []

    def visit(node):
        if isinstance(node, dict):
            keys = {k.lower() for k in node}
            if {"title", "preco"} <= keys or {"title", "price"} <= keys:
                out.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return out


def main() -> None:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    term = (sys.argv[2] if len(sys.argv) > 2 else "lingui").lower()

    api = MeuAtacadaoAppApi()
    api.authenticate()
    print(f"token ok | loja {store} | termo '{term}'")

    print("\n=== categorias ===")
    try:
        categorias = api.get_json(f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store})
        for path, value in walk(categorias):
            if isinstance(value, str) and path.endswith("description"):
                print(f"  {path} = {value}")
    except AppApiError as exc:
        print("  falhou:", exc)
        categorias = {}

    # try the search parameter names the endpoint might accept
    print("\n=== tentando buscar por termo ===")
    search_params = ["search", "nome", "descricao", "termo", "texto", "query", "palavraChave"]
    found_payload = None
    for param in search_params:
        params = {
            "pageNumber": 1,
            "pageSize": 10,
            "onlyWithOffer": "false",
            "filialId": store,
            "idFilial": store,
            param: term,
        }
        try:
            payload = api.get_json(f"{BACKOFFICE}/produto/busca", params)
        except AppApiError as exc:
            print(f"  {param}: {exc}")
            continue
        count = len(products_from(payload))
        print(f"  {param}: {count} produtos")
        if count:
            found_payload = payload
            break

    if found_payload:
        print("\n=== produtos retornados ===")
        for product in products_from(found_payload):
            print(
                f"  {product.get('title')}\n"
                f"      preco={product.get('preco')} finalPrice={product.get('finalPrice')} "
                f"cartao={product.get('finalCardPrice')} ean={product.get('ean')} "
                f"sku={product.get('idSku')} categoria={product.get('category')}"
            )
        (OUT / f"store_{store}_search_{term}.json").write_text(
            json.dumps(found_payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return

    print("\n=== varrendo categorias com produto/busca ===")
    all_products: dict[object, dict] = {}
    category_ids = []
    for path, value in walk(categorias):
        if path.endswith("idCategoria") or path.endswith("categoryId") or path.endswith("id"):
            category_ids.append(value)
    print(f"  categorias encontradas: {sorted(set(map(str, category_ids)))[:30]}")
    for category in sorted(set(map(str, category_ids))):
        for page in range(1, 6):
            params = {
                "idCategoria": category,
                "pageNumber": page,
                "pageSize": 10,
                "onlyWithOffer": "false",
                "filialId": store,
                "idFilial": store,
            }
            try:
                payload = api.get_json(f"{BACKOFFICE}/produto/busca", params)
            except AppApiError as exc:
                print(f"  cat {category} p{page}: {exc}")
                break
            items = products_from(payload)
            if not items:
                break
            for product in items:
                all_products[product.get("idSku") or product.get("title")] = product
    print(f"  produtos coletados: {len(all_products)}")
    (OUT / f"store_{store}_produtos.json").write_text(
        json.dumps(list(all_products.values()), ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"\n=== produtos com '{term}' ===")
    hits = [p for p in all_products.values() if term in str(p.get("title", "")).lower()]
    for product in hits:
        print(
            f"  {product.get('title')}\n"
            f"      preco={product.get('preco')} finalPrice={product.get('finalPrice')} "
            f"cartao={product.get('finalCardPrice')} desconto={product.get('discountPercentage')}% "
            f"ean={product.get('ean')} sku={product.get('idSku')} validade={product.get('validity')}"
        )
    if not hits:
        print("  nada encontrado; amostra de titulos:")
        for product in list(all_products.values())[:30]:
            print("   -", product.get("title"))


if __name__ == "__main__":
    main()
