"""Probe candidate search routes on the app's in-store offers API."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from atacadao_app_api import AppApiError, MeuAtacadaoAppApi  # noqa: E402

STORE = 632
TERM = "linguiça toscana perdigão nabrasa"

CANDIDATES = [
    ("/mobile/ofertas-backoffice/v1/offer/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/offer/list", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/product/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/produto/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/busca-produto", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/oferta/search", {"search": TERM}),
    ("/mobile/ofertas-transacional/v1/search", {"search": TERM}),
    ("/mobile/ofertas-transacional/v1/product/search", {"search": TERM}),
    ("/mobile/ofertas-transacional/v1/offer/list", {"search": TERM}),
    ("/mobile/ofertas-transacional/v1/vitrine/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/vitrine/search", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/offer/search-offers", {"search": TERM}),
    ("/mobile/ofertas-backoffice/v1/offer/busca", {"search": TERM}),
]


def main() -> None:
    api = MeuAtacadaoAppApi()
    api.authenticate()
    print("token ok\n")
    for path, extra in CANDIDATES:
        params = {"pageNumber": 1, "pageSize": 20, "filialId": STORE, "idFilial": STORE, **extra}
        try:
            text = api._get(path, params)
        except AppApiError as exc:
            status = exc.status
            body = exc.body.strip()[:110].replace("\n", " ")
            print(f"  {status} {path}  {body}")
            continue
        print(f"  200 {path} -> {text[:400]}")


if __name__ == "__main__":
    main()
