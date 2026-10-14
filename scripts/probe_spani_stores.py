"""Enumerate Spani store units (CDs) and pull real prices for the Campinas ones.

Credentials and base come from the app bundle (see `scripts/probe_spani_api.py`).
The VIPCommerce API is scoped by `filial` + `centro_distribuicao` (CD): the CD is
the physical store whose price list is served.

Routes that matter (recovered from the app's Angular bundle):

    GET /loja/filial
    GET /loja/filiais/{id}
    GET /loja/centros_distribuicoes/{id}
    GET /filial/{filial}/loja/centros_distribuicoes/retiradas
    GET /filial/{filial}/loja/centros_distribuicoes/cep/{cep}/entrega
    GET /filial/{filial}/centro_distribuicao/{cd}/loja/classificacoes_mercadologicas/departamentos/arvore
    GET /filial/{filial}/centro_distribuicao/{cd}/loja/classificacoes_mercadologicas/departamentos/{id}/produtos
    GET /filial/{filial}/centro_distribuicao/{cd}/loja/produtos/em-oferta/filtros
    GET /filial/{filial}/centro_distribuicao/{cd}/loja/produtos/mais_vendidos/filtros

Usage: python scripts/probe_spani_stores.py [--cidade campinas] [--cd 42]
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
ASSET_BASE = "https://produto-assets-vipcommerce-com-br.br-se1.magaluobjects.com"
OUT = Path(r"C:\Android\capture")

# CEPs of the Campinas region, used to ask the API which CD serves each area.
CAMPINAS_CEPS = {
    "13060-080": "Campinas - Cambuí",
    "13060-646": "Campinas - Jd. Yeda (Atacadão)",
    "13080-395": "Campinas - Dom Pedro",
    "13033-050": "Campinas - Jd. Aurélia",
    "13184-668": "Hortolândia",
    "13472-415": "Americana",
    "13076-000": "Campinas - Taquaral",
}


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


def show(label: str, status: int, body: str, limit: int = 400) -> None:
    marker = "OK " if status == 200 else "   "
    print(f"  {marker}{status:>3} {label}")
    if status == 200 or limit:
        print(f"        {body[:limit]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cd", type=int, default=42, help="centro de distribuição a detalhar")
    args = parser.parse_args()

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        login = client.post(
            f"{API_BASE}/api-admin/v1/org/{ORG}/auth/loja/login",
            json={"domain": DOMAIN, "username": LOJA_USER, "key": LOJA_KEY},
            headers=headers(),
        )
        login.raise_for_status()
        token = login.json()["data"]
        hdr = headers(token)
        base = f"{API_BASE}/api-admin/v1/org/{ORG}"
        print(f"login ok | org {ORG} | {DOMAIN}\n")

        print("=== filial / centros de distribuição ===")
        probes = [
            ("/loja/filial", f"{base}/loja/filial"),
            ("/loja/filiais/1", f"{base}/loja/filiais/1"),
            ("/loja/filiais/2", f"{base}/loja/filiais/2"),
            (f"/loja/centros_distribuicoes/{args.cd}", f"{base}/loja/centros_distribuicoes/{args.cd}"),
            (
                "/filial/1/loja/centros_distribuicoes/retiradas",
                f"{base}/filial/1/loja/centros_distribuicoes/retiradas",
            ),
            (
                "/filial/1/centro_distribuicao/42",
                f"{base}/filial/1/centro_distribuicao/42",
            ),
        ]
        for cep, label in CAMPINAS_CEPS.items():
            probes.append(
                (
                    f"/filial/1/loja/centros_distribuicoes/cep/{cep.replace('-', '')}/entrega  ({label})",
                    f"{base}/filial/1/loja/centros_distribuicoes/cep/{cep.replace('-', '')}/entrega",
                )
            )

        findings: dict[str, dict[str, object]] = {}
        for label, url in probes:
            try:
                response = client.get(url, headers=hdr)
            except httpx.HTTPError as exc:
                show(label, 0, f"{type(exc).__name__}: {exc}")
                continue
            show(label, response.status_code, response.text)
            findings[label] = {"url": url, "status": response.status_code, "body": response.text[:4000]}

        # ------------------------------------------------------------- prices
        filial, cd = 1, args.cd
        prefix = f"{base}/filial/{filial}/centro_distribuicao/{cd}"
        print(f"\n=== catálogo/preço do CD {cd} ===")
        tree_response = client.get(
            f"{prefix}/loja/classificacoes_mercadologicas/departamentos/arvore", headers=hdr
        )
        show("arvore de departamentos", tree_response.status_code, tree_response.text, 500)
        tree = (tree_response.json() or {}).get("data") or []
        if tree:
            first = tree[0]
            dept_id = first["classificacao_mercadologica_id"]
            print(
                f"\n  departamentos: "
                + ", ".join(f"{node['classificacao_mercadologica_id']}={node.get('descricao')}" for node in tree)
            )
            products_response = client.get(
                f"{prefix}/loja/classificacoes_mercadologicas/departamentos/{dept_id}/produtos",
                params={"page": 1, "limit": 5},
                headers=hdr,
            )
            show(f"produtos do departamento {dept_id}", products_response.status_code, products_response.text, 300)
            payload = products_response.json() if products_response.status_code == 200 else {}
            for raw in (payload.get("data") or [])[:5]:
                offer = raw.get("oferta") or {}
                print(
                    f"    {str(raw.get('descricao'))[:52]:<52} preco={raw.get('preco')} "
                    f"oferta={offer.get('preco_oferta')} antigo={offer.get('preco_antigo')} "
                    f"disponivel={raw.get('disponivel')} ean={raw.get('codigo_barras')}"
                )
            findings["sample"] = {"department": dept_id, "products": (payload.get("data") or [])[:5]}

        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / "spani_store_probe.json"
        path.write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nresultado -> {path}")


if __name__ == "__main__":
    main()
