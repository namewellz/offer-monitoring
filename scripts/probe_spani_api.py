"""Probe the Spani (VIPCommerce tenant 67) API for branch and price routes.

The "Spani Atacadista" app (`br.com.spanionline.appvendas`) is a Capacitor/Angular
bundle, so its whole configuration is readable JavaScript. Extracted from
`assets/public/chunk-2BEEEPJT.js`:

    apiServicesUrl: https://services.vipcommerce.com.br
    lojaUser: "loja"
    lojaAuthJWT: "df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469"
    isApp: true
    apiUrl: https://services-beta.vipcommerce.com.br/api-admin/v1
    wsUrl:  https://services-beta.vipcommerce.com.br/ws
    idAplicativo: 72
    domainKey: "spanionline.com.br"
    orgId: 67

This script logs in with the storefront credential and then walks a candidate
list of routes to find: the branches (filiais), their distribution centres (CDs)
and the product/price endpoints, so a collector can price each physical store.

Usage: python scripts/probe_spani_api.py [--candidate-file out.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

API_BASE = "https://services-beta.vipcommerce.com.br"
API_SERVICES = "https://services.vipcommerce.com.br"
ORG = "67"
DOMAIN = "spanionline.com.br"
LOJA_USER = "loja"
LOJA_KEY = "df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469"
OUT = Path(r"C:\Android\capture")


def headers(base: str, token: str | None = None) -> dict[str, str]:
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


def try_get(client: httpx.Client, url: str, hdr: dict[str, str]) -> tuple[int, str]:
    try:
        response = client.get(url, headers=hdr)
    except httpx.HTTPError as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    body = response.text
    return response.status_code, body[:600]


def main() -> None:
    candidate_file = None
    if "--candidate-file" in sys.argv:
        candidate_file = sys.argv[sys.argv.index("--candidate-file") + 1]

    with httpx.Client(timeout=45, follow_redirects=True) as client:
        # ---------------------------------------------------------------- login
        for base in (API_BASE, API_SERVICES):
            url = f"{base}/api-admin/v1/org/{ORG}/auth/loja/login"
            try:
                response = client.post(
                    url,
                    json={"domain": DOMAIN, "username": LOJA_USER, "key": LOJA_KEY},
                    headers=headers(base),
                )
            except httpx.HTTPError as exc:
                print(f"login {base}: {type(exc).__name__}: {exc}")
                continue
            payload = response.json() if response.status_code == 200 else None
            token = (payload or {}).get("data")
            print(f"login {base}: HTTP {response.status_code} token={'ok' if token else 'none'}")
            if token:
                api_base = base
                break
        else:
            print("login falhou nas duas bases")
            return

        hdr = headers(api_base, token)

        # ----------------------------------------------------- candidate routes
        candidates = [
            "/loja/filiais",
            "/loja/filiais/lista",
            "/loja/filial",
            "/loja/televendas/filiais",
            "/loja/centros_distribuicao",
            "/loja/cd",
            "/loja/unidades",
            "/loja/sessao_cliente",
            "/loja/parametros",
            "/filiais",
            "/filial/1/centro_distribuicao",
            "/loja/classificacoes_mercadologicas/departamentos/arvore",
            "/loja/classificacoes_mercadologicas/departamentos/arvore/filial/1",
            "/filial/1/loja/classificacoes_mercadologicas/departamentos/arvore",
            "/filiais/1",
            "/filiais/1/aplicativos",
            "/aplicativos/72",
            "/loja/ofertas",
            "/loja/produtos",
        ]
        results: dict[str, dict[str, object]] = {}
        print(f"\n=== sondando rotas em {api_base}/api-admin/v1/org/{ORG} ===")
        for candidate in candidates:
            url = f"{api_base}/api-admin/v1/org/{ORG}{candidate}"
            status, body = try_get(client, url, hdr)
            marker = "OK " if status == 200 else "   "
            print(f"  {marker}{status:>3} {candidate}   {body[:120]}")
            results[candidate] = {"status": status, "body": body}

        if candidate_file:
            Path(candidate_file).write_text(
                json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"\nresultado -> {candidate_file}")


if __name__ == "__main__":
    main()
