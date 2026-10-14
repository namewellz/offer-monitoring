"""Probe how Spani/VIPCommerce exposes *offers* (promotional prices) per store.

The department listing (`.../departamentos/{id}/produtos`) answers with
``em_oferta: false`` and no ``oferta`` object, so offers must come from another
route. This script walks the candidates the app bundle mentions:

    /loja/produtos/em-oferta/filtros
    /loja/produtos/mais_vendidos/filtros
    /loja/vitrines/produtos/disponiveis/filtros
    /loja/ofertas/tag/{tag}/produtos/filtros
    /filial/{f}/centro_distribuicao/{cd}/loja/produtos/em-oferta
    /filial/{f}/centro_distribuicao/{cd}/loja/vitrines/dedicadas

Usage: python scripts/probe_spani_offers.py [--cd 42]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

API_BASE = "https://services-beta.vipcommerce.com.br"
ORG = "67"
DOMAIN = "spanionline.com.br"
LOJA_USER = "loja"
LOJA_KEY = "df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469"
OUT = Path(r"C:\Android\capture")


def headers(token: str | None = None) -> dict[str, str]:
    result = {
        "domainkey": DOMAIN,
        "organizationid": ORG,
        "Accept": "application/json",
        "User-Agent": "Spani/1.146.1 (Android)",
    }
    if token:
        result["Authorization"] = f"Bearer {token}"
        result["sessao-id"] = "offer-monitoring"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cd", type=int, default=42)
    args = parser.parse_args()

    with httpx.Client(timeout=90, follow_redirects=True) as client:
        login = client.post(
            f"{API_BASE}/api-admin/v1/org/{ORG}/auth/loja/login",
            json={"domain": DOMAIN, "username": LOJA_USER, "key": LOJA_KEY},
            headers=headers(),
        )
        login.raise_for_status()
        token = login.json()["data"]
        hdr = headers(token)
        base = f"{API_BASE}/api-admin/v1/org/{ORG}"
        prefix = f"{base}/filial/1/centro_distribuicao/{args.cd}/loja"

        candidates = [
            f"{prefix}/produtos/em-oferta",
            f"{prefix}/produtos/em-oferta/filtros",
            f"{prefix}/produtos/mais_vendidos/filtros",
            f"{prefix}/vitrines/produtos/disponiveis/filtros",
            f"{prefix}/vitrines/produtos/filtros",
            f"{prefix}/vitrines/dedicadas",
            f"{prefix}/ofertas/tag/oferta-exclusiva/produtos/filtros",
            f"{base}/loja/produtos/em-oferta/filtros",
        ]
        results: dict[str, object] = {}
        for url in candidates:
            try:
                response = client.get(url, params={"page": 1, "limit": 20}, headers=hdr)
            except httpx.HTTPError as exc:
                print(f"      {type(exc).__name__}: {exc}  {url}")
                continue
            marker = "OK " if response.status_code == 200 else "   "
            print(f"  {marker}{response.status_code:>3} {url.replace(base, '')}")
            if response.status_code == 200:
                payload = response.json()
                sample = payload.get("data")
                size = len(sample) if isinstance(sample, list) else "?"
                print(f"        data={size}  keys={sorted(payload.keys())}")
                if isinstance(sample, list) and sample:
                    print("        primeiro:", json.dumps(sample[0], ensure_ascii=False)[:400])
                elif isinstance(sample, dict):
                    print("        dict:", json.dumps(sample, ensure_ascii=False)[:400])
            results[url] = {"status": response.status_code, "body": response.text[:2000]}

        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"spani_offers_probe_cd{args.cd}.json"
        path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nresultado -> {path}")


if __name__ == "__main__":
    main()
