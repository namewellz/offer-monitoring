"""Look up an Atacadao product by EAN on the public flyer-services API.

GET {BASE}/api/v2/Product/{productRef}?api-version=2  -> "productRef" is a route
parameter (passing a name yields 400 "The value 'Search' is not valid").

Validated against the LinguiÃ§a Toscana PerdigÃ£o Nabrasa at store 632 (HortolÃ¢ndia).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"
VTEX = "https://atacadaobr.vtexcommercestable.com.br/api/catalog_system/pub/products/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
QUERY = "LinguiÃ§a Toscana PerdigÃ£o Nabrasa"


def get(url: str, accept: str = "*/*") -> tuple[int, str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": accept, "Origin": "https://www.atacadao.com.br"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def vtex_candidates() -> list[dict]:
    url = f"{VTEX}?ft={urllib.parse.quote(QUERY)}&_from=0&_to=9"
    status, text = get(url)
    print(f"VTEX search: {status}, {len(text)} bytes")
    if status not in (200, 206):
        print(text[:300])
        return []
    out = []
    for raw in json.loads(text):
        for item in raw.get("items") or []:
            out.append(
                {
                    "productName": raw.get("productName"),
                    "productId": raw.get("productId"),
                    "ean": item.get("ean"),
                    "itemId": item.get("itemId"),
                    "nameComplete": item.get("nameComplete"),
                }
            )
    return out


def main() -> None:
    cands = vtex_candidates()
    for c in cands:
        print("  ", c)
    if not cands:
        return

    print("\n=== flyer-services /api/v2/Product/{ref} ===")
    for c in cands[:4]:
        for ref in filter(None, [c["ean"], c["productId"], c["itemId"]]):
            for extra in ("", "&storeId=632"):
                url = f"{BASE}/api/v2/Product/{urllib.parse.quote(str(ref))}?api-version=2{extra}"
                status, text = get(url)
                print(f"  {status} ref={ref} extra='{extra}' len={len(text)}")
                if status == 200:
                    print("       " + text[:600].replace("\n", " "))


if __name__ == "__main__":
    main()

