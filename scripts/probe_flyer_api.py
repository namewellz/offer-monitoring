"""Probe the Carrefour/Atacadao public flyer-services API.

Discovered from https://www.atacadao.com.br/institucional/nossas-lojas:
    https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services/api/v2/Store/city
No credentials are required for the store endpoints; the goal is to find the
flyer-product endpoints that carry prices per store (store 632 = Hortolandia).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"


def get(path: str, params: dict | None = None, timeout: int = 30) -> tuple[int, str, dict]:
    url = BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://www.atacadao.com.br"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc), {}


def main() -> None:
    print("=== stores for Hortolandia ===")
    status, text, _ = get("/api/v2/Store/city", {"uf": "SP", "city": "Hortolândia", "PageSize": "24", "pageNumber": "1", "api-version": "2"})
    print(status, text[:1200])

    print("\n=== city/uf ===")
    status, text, _ = get("/api/v2/Store/city/uf", {"uf": "SP", "api-version": "2"})
    try:
        cities = json.loads(text)
        print(status, "cities:", len(cities) if isinstance(cities, list) else str(cities)[:200])
    except Exception:
        print(status, text[:300])

    probes = [
        ("/api/v2/Store/632", {"api-version": "2"}),
        ("/api/v2/Store/632/flyers", {"api-version": "2"}),
        ("/api/v2/Flyer/Store/632", {"api-version": "2"}),
        ("/api/v2/Flyer/store/632", {"api-version": "2"}),
        ("/api/v2/Flyer/632", {"api-version": "2"}),
        ("/api/v2/Flyer/list", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/byStore", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/ByZipCode", {"zipCode": "13184668", "api-version": "2"}),
        ("/api/v2/Flyer/Pdf", {"id": "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo", "api-version": "2"}),
        ("/api/v2/Flyer/Page", {"id": "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo", "api-version": "2"}),
        ("/api/v2/Flyer/Product", {"id": "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo", "api-version": "2"}),
        ("/api/v2/Flyer/Products", {"id": "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo", "api-version": "2"}),
        ("/api/v2/Flyer/Offer", {"id": "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo", "api-version": "2"}),
        ("/api/v2/Flyer/Search", {"q": "linguica", "storeId": "632", "api-version": "2"}),
        ("/api/v1/Flyer/Store/632", {"api-version": "2"}),
        ("/api/v1/busca/loc/", {"q": "hortolandia", "api-version": "2"}),
        ("/api/v1/busca/cep/", {"cep": "13184668", "api-version": "2"}),
        ("/api/v1/store-info", {"storeId": "632", "api-version": "2"}),
        ("/swagger/index.html", None),
        ("/swagger/v1/swagger.json", None),
        ("/openapi.json", None),
        ("/api-docs", None),
    ]
    print("\n=== endpoint probing ===")
    for path, params in probes:
        status, text, headers = get(path, params)
        ctype = headers.get("Content-Type", "")
        print(f"  {status:>4} {path}{'?' + urllib.parse.urlencode(params) if params else ''}")
        if status == 200:
            print(f"        {ctype} :: {text[:260].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
