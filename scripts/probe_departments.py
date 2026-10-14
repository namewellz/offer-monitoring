"""Check how the app's product search partitions the store by department.

For each top-level category of `home/categorias`, asks `produto/busca` how many
products it has and whether the sum equals the whole-store sweep.

Usage: python scripts/probe_departments.py [store]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

BACKOFFICE = "/mobile/ofertas-backoffice/v1"
PAGE_SIZE = 50  # server-side maximum


def count(api: MeuAtacadaoAppApi, store: int, categoria: str | None) -> int | None:
    params = {
        "pageNumber": 1,
        "pageSize": PAGE_SIZE,
        "onlyWithOffer": "false",
        "filialId": store,
        "idFilial": store,
    }
    if categoria is not None:
        params["idCategoria"] = categoria
    try:
        payload = api.get_json(f"{BACKOFFICE}/produto/busca", params)
    except AppApiError as exc:
        print(f"      erro: {exc}")
        return None
    return int(payload.get("totalItems") or 0)


def main() -> None:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    api = MeuAtacadaoAppApi()
    api.authenticate()

    categorias = api.get_json(
        f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store}
    )
    total_loja = count(api, store, None)
    print(f"loja {store}: catalogo completo = {total_loja} produtos\n")

    soma = 0
    for categoria in categorias:
        identificador = categoria["idCategoria"]
        nome = categoria["category"]
        quantidade = count(api, store, identificador)
        if quantidade is None:
            continue
        soma += quantidade
        ofertas = categoria.get("totalOfertas")
        print(f"  {identificador:>5}  {nome:<38} produtos={quantidade:>5}  ofertas={ofertas}")

    print(f"\nsoma dos departamentos = {soma}")
    print(f"catalogo completo     = {total_loja}")
    print(f"diferenca             = {(total_loja or 0) - soma}")


if __name__ == "__main__":
    main()
