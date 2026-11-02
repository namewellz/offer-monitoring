"""Health probe for the Atacadão app API (edge-function proxy).

Since app 13.429.2 the in-store offers API is reached through a Supabase edge
function that keeps the Keycloak service credentials server-side, so there is no
token to inspect anymore - the only things that can be verified are the API key
and the routes.

Run it after rotating the key or when a collection fails:

    python scripts/probe_app_api_health.py            # loja 632 (Hortolândia)
    python scripts/probe_app_api_health.py 662        # outra filial

It fails loudly (exit 1) when the key is rejected or a route regressed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = (
    "https://txgwdepbtdvfnubmtewb.supabase.co/functions/v1/atacadao-in-store-offers"
)
BASE = os.environ.get("ATACADAO_APP_BASE_URL", DEFAULT_BASE).rstrip("/")
BACKOFFICE = "/mobile/ofertas-backoffice/v1"
UA = "Dart/3.10 (dart:io)"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set (see .env.production.example)")
    return value


API_KEY = _require_env("ATACADAO_APP_API_KEY")


def get(path: str, params: dict | None = None) -> tuple[int, str, float]:
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "x-api-key": API_KEY,
            "apikey": API_KEY,
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if raw[:2] == b"\x1f\x8b":
            import gzip

            raw = gzip.decompress(raw)
        return exc.code, raw.decode("utf-8", "replace"), time.perf_counter() - started


def main() -> int:
    store = int(sys.argv[1]) if len(sys.argv) > 1 else 632
    print(f"edge function: {BASE}")
    print(f"filial       : {store}\n")

    checks = [
        ("offer/status", f"{BACKOFFICE}/offer/status", {"filialId": store, "idFilial": store}),
        ("home/categorias", f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store}),
        (
            "produto/busca",
            f"{BACKOFFICE}/produto/busca",
            {
                "idCategoria": 2,
                "pageNumber": 1,
                "pageSize": 3,
                "onlyWithOffer": "false",
                "filialId": store,
                "idFilial": store,
            },
        ),
        (
            "busca-loja-via-cidade-nome/v2",
            f"{BACKOFFICE}/busca-loja-via-cidade-nome/v2",
            {"page": 1, "pageSize": 3, "cityOrName": "hortolandia", "lat": 0.0, "lon": 0.0},
        ),
    ]

    failed = 0
    for label, path, params in checks:
        status, body, elapsed = get(path, params)
        ok = status == 200
        failed += 0 if ok else 1
        print(f"{label:<32} {status} {elapsed * 1000:6.0f} ms  {body[:120].replace(chr(10), ' ')}")

    if failed:
        print(f"\n{failed} rota(s) falharam - a chave ou o contrato mudou.")
        return 1

    status, body, _ = get(
        f"{BACKOFFICE}/produto/busca",
        {
            "idCategoria": 13,
            "pageNumber": 1,
            "pageSize": 5,
            "onlyWithOffer": "true",
            "filialId": store,
            "idFilial": store,
        },
    )
    if status == 200:
        payload = json.loads(body)
        sample = (payload.get("Produtos") or [{}])[0]
        print("\nexemplo com oferta ativa (Carnes, aves e peixes):")
        for field in ("title", "ean", "preco", "finalPrice", "finalCardPrice"):
            print(f"  {field:<14} {sample.get(field)}")
    print("\nOK - credencial e rotas validas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
