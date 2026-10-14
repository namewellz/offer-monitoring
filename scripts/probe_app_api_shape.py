"""Probe the shape/limits of the in-store offers API used by the Meu Atacadao app.

Answers, for a given branch:
  * what `home/categorias` returns (field names / ids)
  * which page sizes `produto/busca` accepts
  * whether `produto/busca` works without `idCategoria` (whole-store sweep)
  * how many products each strategy exposes

Usage: python scripts/probe_app_api_shape.py [store]        (default 632 Hortolandia)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

BACKOFFICE = "/mobile/ofertas-backoffice/v1"
OUT = Path(r"C:\Android\capture")


def skeleton(node, depth=0, max_depth=4):
    pad = "  " * depth
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                print(f"{pad}{key}: {type(value).__name__}({len(value)})")
                if depth < max_depth:
                    skeleton(value, depth + 1, max_depth)
            else:
                print(f"{pad}{key} = {value!r}")
    elif isinstance(node, list):
        if node:
            print(f"{pad}[0] ->")
            skeleton(node[0], depth + 1, max_depth)


def produtos(payload) -> list[dict]:
    return (payload or {}).get("Produtos") or []


def main() -> None:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    api = MeuAtacadaoAppApi()
    api.authenticate()
    print(f"token ok | loja {store}\n")

    print("=== home/categorias ===")
    categorias = api.get_json(f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store})
    skeleton(categorias, max_depth=3)
    (OUT / f"store_{store}_categorias.json").write_text(
        json.dumps(categorias, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("\n=== produto/busca: pageSize limits (sem idCategoria) ===")
    for size in (10, 25, 50, 51, 100):
        try:
            payload = api.get_json(
                f"{BACKOFFICE}/produto/busca",
                {
                    "pageNumber": 1,
                    "pageSize": size,
                    "onlyWithOffer": "false",
                    "filialId": store,
                    "idFilial": store,
                },
            )
        except AppApiError as exc:
            print(f"  pageSize={size}: {exc}")
            continue
        print(
            f"  pageSize={size}: items={len(produtos(payload))} "
            f"totalItems={payload.get('totalItems')} totalPages={payload.get('totalPages')}"
        )

    print("\n=== produto/busca sem categoria, paginando (pageSize=50) ===")
    seen: dict[int, dict] = {}
    page = 1
    while page <= 300:
        try:
            payload = api.get_json(
                f"{BACKOFFICE}/produto/busca",
                {
                    "pageNumber": page,
                    "pageSize": 50,
                    "onlyWithOffer": "false",
                    "filialId": store,
                    "idFilial": store,
                },
            )
        except AppApiError as exc:
            print(f"  pagina {page}: {exc}")
            break
        items = produtos(payload)
        if not items:
            break
        before = len(seen)
        for item in items:
            seen[int(item["idSku"])] = item
        if page % 10 == 1 or page == int(payload.get("totalPages") or 0):
            print(f"  p{page}: {len(items)} itens (+{len(seen) - before} novos) total={len(seen)}/{payload.get('totalItems')}")
        if page >= int(payload.get("totalPages") or 0):
            break
        page += 1
    print(f"  total unico sem categoria: {len(seen)}")

    print("\n=== produto/busca idCategoria=13 ===")
    try:
        payload = api.get_json(
            f"{BACKOFFICE}/produto/busca",
            {
                "idCategoria": 13,
                "pageNumber": 1,
                "pageSize": 50,
                "onlyWithOffer": "false",
                "filialId": store,
                "idFilial": store,
            },
        )
        print(f"  items={len(produtos(payload))} totalItems={payload.get('totalItems')} totalPages={payload.get('totalPages')}")
        for item in produtos(payload)[:3]:
            print(f"   - {item.get('title')} | {item.get('category')} | cat={item.get('idCategoria')}")
    except AppApiError as exc:
        print(f"  {exc}")

    print("\n=== onlyWithOffer=true ===")
    try:
        payload = api.get_json(
            f"{BACKOFFICE}/produto/busca",
            {
                "pageNumber": 1,
                "pageSize": 50,
                "onlyWithOffer": "true",
                "filialId": store,
                "idFilial": store,
            },
        )
        print(f"  items={len(produtos(payload))} totalItems={payload.get('totalItems')} totalPages={payload.get('totalPages')}")
    except AppApiError as exc:
        print(f"  {exc}")


if __name__ == "__main__":
    main()
