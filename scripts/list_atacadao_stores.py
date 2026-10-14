"""List Atacadao stores from the public flyer-services API (all 389 branches)."""
from __future__ import annotations

import re
import sys
import unicodedata
import urllib.request
import json

BASE = "https://apigw.cloud.carrefour.com.br/api-middleware-flyer-services"

REGIONS = (
    "campinas|hortolandia|americana|sumare|indaiatuba|itu|jundiai|santa barbara|"
    "valinhos|vinhedo|paulinia|cosmopolis|artur nogueira|holambra|monte mor|"
    "santa barbara d'oeste|pedreira|jaguariuna"
)


def norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def fetch_page(page: int) -> dict:
    url = f"{BASE}/api/v2/Store/all?api-version=2&pageNumber={page}&PageSize=50"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def main() -> None:
    pattern = re.compile(sys.argv[1] if len(sys.argv) > 1 else REGIONS, re.I)
    stores: list[dict] = []
    page, pages = 1, 1
    while page <= pages:
        payload = fetch_page(page)
        stores.extend(payload["stores"])
        pages = payload["totalPages"]
        page += 1
    print(f"{len(stores)} stores fetched (totalItems={payload['totalItems']}, pages={pages})")
    print(f"--- stores matching /{pattern.pattern}/ ---")
    for store in stores:
        haystack = norm(f"{store['loja']} {store['cidade']}")
        if pattern.search(haystack):
            print(
                f"  {store['storeId']:>5}  {store['loja']:<40} {store['cidade']:<20} "
                f"CEP {store['cep']:<10} tipo {store['tipoLoja']}"
            )


if __name__ == "__main__":
    main()
