"""Client for the 'Meu Atacadao' app in-store offers API (freyr/Carrefour).

Credentials and routes were recovered from the real app (see
/memories/repo/atacadao-app-api-and-flyers.md):

    POST {base}/infosec/auth/v1/protocol/openid-connect/token
        grant_type=password & client_id=OfertaMobile-TokenAuth
        username=kcc-ofertas-externo & password=... & client_secret=...

    GET  {base}/mobile/ofertas-backoffice/v1/...   (Authorization: Bearer <jwt>)
        home/banners | home/categorias | offer/status
        busca-loja-via-cep/v2 | busca-loja-via-cidade-nome/v2 | busca-loja-via-geolocation/v2
        vitrine/mobile/v2 | vitrine-details/mobile/v2

Every store-scoped route takes `filialId` and `idFilial` (the store number).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://freyr.portal.atacadao.com.br"
BACKOFFICE = "/mobile/ofertas-backoffice/v1"
TRANSACTIONAL = "/mobile/ofertas-transacional/v1"

TOKEN_PATH = "/infosec/auth/v1/protocol/openid-connect/token"
CLIENT_ID = "OfertaMobile-TokenAuth"
CLIENT_SECRET = "CI4hKA5gdaXjDLm52Mz68pXOhIhiUvNA"
USERNAME = "kcc-ofertas-externo"
PASSWORD = "WUzN!r2Jrr!8BTFteoW3J"
UA = "Dart/3.10 (dart:io)"


class AppApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def _request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
) -> tuple[int, str]:
    request_headers = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


class MeuAtacadaoAppApi:
    def __init__(self, base: str = BASE):
        self.base = base.rstrip("/")
        self.token: str | None = None

    # ---------------------------------------------------------------- auth
    def authenticate(self) -> str:
        form = urllib.parse.urlencode(
            {
                "grant_type": "password",
                "username": USERNAME,
                "password": PASSWORD,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        ).encode()
        status, text = _request(
            self.base + TOKEN_PATH,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status != 200:
            raise AppApiError(status, text)
        payload = json.loads(text)
        self.token = payload["access_token"]
        return self.token

    def _get(self, path: str, params: dict | None = None) -> str:
        if not self.token:
            self.authenticate()
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        status, text = _request(url, headers={"Authorization": f"Bearer {self.token}"})
        if status == 401:
            self.authenticate()
            status, text = _request(url, headers={"Authorization": f"Bearer {self.token}"})
        if status != 200:
            raise AppApiError(status, text)
        return text

    def get_json(self, path: str, params: dict | None = None):
        return json.loads(self._get(path, params))

    # -------------------------------------------------------------- stores
    def stores_by_city(self, city: str, page_size: int = 20) -> dict:
        return self.get_json(
            f"{BACKOFFICE}/busca-loja-via-cidade-nome/v2",
            {"page": 1, "pageSize": page_size, "cityOrName": city, "lat": 0.0, "lon": 0.0},
        )

    def stores_by_cep(self, cep: str, page_size: int = 20) -> dict:
        return self.get_json(
            f"{BACKOFFICE}/busca-loja-via-cep/v2",
            {"page": 1, "pageSize": page_size, "cep": cep, "lat": 0.0, "lon": 0.0},
        )

    # ------------------------------------------------------------ in-store
    def offer_status(self, store: int) -> dict:
        return self.get_json(f"{BACKOFFICE}/offer/status", {"filialId": store, "idFilial": store})

    def categories(self, store: int) -> dict:
        return self.get_json(f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store})

    def banners(self, store: int) -> dict:
        return self.get_json(f"{BACKOFFICE}/home/banners", {"filialId": store, "idFilial": store})

    def showcase(self, store: int, page: int = 1, page_size: int = 10, products: int = 5) -> dict:
        return self.get_json(
            f"{BACKOFFICE}/vitrine/mobile/v2",
            {
                "pageNumber": page,
                "pageSize": page_size,
                "pageProductSize": products,
                "filialId": store,
                "idFilial": store,
            },
        )

    def showcase_details(self, store: int, showcase_id: str | int, page: int = 1, page_size: int = 20) -> dict:
        return self.get_json(
            f"{BACKOFFICE}/vitrine-details/mobile/v2",
            {
                "idVitrine": showcase_id,
                "pageNumber": page,
                "pageSize": page_size,
                "filialId": store,
                "idFilial": store,
            },
        )

    def search_offers(self, store: int, term: str, page: int = 1, page_size: int = 20) -> dict:
        """Search inside the store's offers (endpoint used by /in_store_offers/search_offers)."""
        return self.get_json(
            f"{TRANSACTIONAL}/offer/search",
            {
                "pageNumber": page,
                "pageSize": page_size,
                "search": term,
                "filialId": store,
                "idFilial": store,
            },
        )


if __name__ == "__main__":
    api = MeuAtacadaoAppApi()
    token = api.authenticate()
    print(f"token ok ({len(token)} chars)")
    print("offer status:", api.offer_status(632))
