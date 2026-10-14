"""Deep probe of the flyer-services API: full store payload + product-ish routes."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
FLYER = "1MjkxSO2xyHCxHerbBTEdrAglQBvt68ZU"
THUMB = "1am2bonqnJKLd4wQPmA3yZCSlcPT1nIeo"


def get(path: str, params: dict | None = None) -> tuple[int, str]:
    url = BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Origin": "https://www.atacadao.com.br"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> None:
    status, text = get("/api/v2/Store/632", {"api-version": "2"})
    print("=== full store 632 payload ===")
    try:
        print(json.dumps(json.loads(text), ensure_ascii=False, indent=1)[:4000])
    except Exception:
        print(status, text[:500])

    print("\n=== product-ish route probing ===")
    routes = [
        ("/api/v2/Product/Search", {"q": "linguica", "api-version": "2"}),
        ("/api/v2/Product/search", {"q": "linguica", "api-version": "2"}),
        ("/api/v2/Products", {"api-version": "2"}),
        ("/api/v2/Offer/List", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/info", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/detail", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/details", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/pages/", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/page/", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/hotspot", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/hotspots", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/items", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/product", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/products", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/offers", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/catalog", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/json", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/byId", {"id": FLYER, "api-version": "2"}),
        ("/api/v2/Flyer/store", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/stores", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/listByStore", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/validity", {"storeId": "632", "api-version": "2"}),
        ("/api/v2/Flyer/thumb", {"id": THUMB, "api-version": "2"}),
        ("/api/v2/Flyer/thumbnail/", {"id": THUMB, "api-version": "2"}),
        ("/api/v2/Store/all", {"api-version": "2"}),
        ("/api/v2/Store/list", {"api-version": "2"}),
        ("/api/v2/Store/uf", {"uf": "SP", "api-version": "2"}),
        ("/api/v2/Store/state", {"uf": "SP", "api-version": "2"}),
        ("/api/v2/Store/zipcode", {"zipCode": "13184668", "api-version": "2"}),
        ("/api/v1/Store/city", {"uf": "SP", "city": "Hortolândia", "PageSize": "24", "pageNumber": "1", "api-version": "1"}),
    ]
    for path, params in routes:
        status, text = get(path, params)
        ctype = "json" if text.lstrip().startswith(("{", "[")) else ("pdf" if text.startswith("%PDF") else "other")
        print(f"  {status:>4} {ctype:<5} {path}?{urllib.parse.urlencode(params)}")
        if status == 200 and ctype == "json":
            print("        " + text[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
