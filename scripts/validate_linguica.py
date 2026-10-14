"""Validate the in-store price of 'Linguiça Toscana Perdigão Nabrasa' at Hortolândia (632)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

STORE = 632
TERM = "lingui"


def walk(node, path="") -> list[tuple[str, object]]:
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(walk(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(walk(value, f"{path}[{index}]"))
    else:
        out.append((path, node))
    return out


def main() -> None:
    api = MeuAtacadaoAppApi()
    api.authenticate()
    print("token ok")

    stores = api.stores_by_city("hortolandia")
    print("busca loja:", json.dumps(stores, ensure_ascii=False)[:300])

    print("\n=== estrutura da vitrine (loja 632) ===")
    showcase = api.showcase(STORE, page=1, page_size=2, products=2)
    print(json.dumps(showcase, ensure_ascii=False)[:1500])

    print("\n=== search_offers tenta o endpoint transacional ===")
    try:
        result = api.search_offers(STORE, "linguiça toscana perdigão nabrasa")
        print(json.dumps(result, ensure_ascii=False)[:800])
    except AppApiError as exc:
        print("  falhou:", exc)

    print("\n=== procurando 'lingui' na vitrine (varias paginas) ===")
    hits = []
    for page in range(1, 11):
        try:
            data = api.showcase(STORE, page=page, page_size=10, products=20)
        except AppApiError as exc:
            print(f"  pagina {page}: {exc}")
            break
        text = json.dumps(data, ensure_ascii=False)
        for path, value in walk(data):
            if isinstance(value, str) and TERM in value.lower():
                hits.append((page, path, value))
        if not data:
            break
    if hits:
        for page, path, value in hits:
            print(f"  p{page} {path} = {value}")
    else:
        print("  nenhum produto com 'lingui' na vitrine")

    print("\n=== nomes de produtos disponiveis (amostra) ===")
    data = api.showcase(STORE, page=1, page_size=5, products=20)
    seen = []
    for path, value in walk(data):
        if isinstance(value, str) and path.endswith("description") or path.endswith("name"):
            seen.append(f"{path}={value}")
    for item in seen[:40]:
        print("  ", item)


if __name__ == "__main__":
    main()
