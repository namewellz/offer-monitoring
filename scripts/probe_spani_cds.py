"""Enumerate every Spani store unit (CD) and compare prices across Campinas stores.

Evidence run for the "Spani Atacadista" app (`br.com.spanionline.appvendas`
1.146.1). The app config, extracted from `assets/public/chunk-2BEEEPJT.js`:

    apiUrl:  https://services-beta.vipcommerce.com.br/api-admin/v1
    domainKey: "spanionline.com.br"      orgId: 67     idAplicativo: 72
    lojaUser: "loja"  lojaAuthJWT: df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469

Routes used (all present in the app bundle, all answering with the storefront
credential — no operator login needed):

    GET /loja/filiais/1
    GET /filial/1/loja/centros_distribuicoes/retiradas
    GET /filial/1/loja/centros_distribuicoes/cep/{cep}/entrega
    GET /filial/1/centro_distribuicao/{cd}/loja/classificacoes_mercadologicas/departamentos/arvore
    GET /filial/1/centro_distribuicao/{cd}/loja/classificacoes_mercadologicas/departamentos/{id}/produtos

Usage: python scripts/probe_spani_cds.py [--compare "arroz,leite"]
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

CAMPINAS_CEPS = [
    "13060080",
    "13060646",
    "13080395",
    "13033050",
    "13076000",
    "13097171",
    "13184668",
    "13472415",
]


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


def summarize_store(raw: dict) -> dict:
    address = raw.get("endereco") or {}
    coords = raw.get("coordenada_geografica") or {}
    return {
        "id": raw.get("centro_distribuicao_id") or raw.get("id"),
        "nome": raw.get("nome_site") or raw.get("nome"),
        "cnpj": raw.get("cnpj"),
        "cep": address.get("cep"),
        "endereco": " ".join(
            str(part) for part in (address.get("logradouro"), address.get("numero")) if part
        ).strip(),
        "bairro": address.get("bairro"),
        "cidade": address.get("cidade"),
        "estado": address.get("estado"),
        "latitude": coords.get("latitude"),
        "longitude": coords.get("longitude"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", default="arroz,leite,cerveja")
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
        evidence: dict[str, object] = {}

        filial = client.get(f"{base}/loja/filiais/1", headers=hdr).json().get("data") or {}
        print(f"filial: {filial.get('vipcommerce_filial_id')}  {filial.get('nome')}")
        evidence["filial"] = filial

        print("\n=== centros de distribuição (unidades) ===")
        retiradas = client.get(
            f"{base}/filial/1/loja/centros_distribuicoes/retiradas", headers=hdr
        ).json()
        stores = [summarize_store(raw) for raw in (retiradas.get("data") or [])]
        for store in sorted(stores, key=lambda item: str(item["cidade"])):
            print(
                f"  cd {str(store['id']):>4}  {str(store['nome'])[:34]:<34} "
                f"{str(store['cidade'])[:18]:<18} {store['estado']}  cep {store['cep']}"
            )
        evidence["retiradas"] = stores
        print(f"  total: {len(stores)}")

        print("\n=== CDs por CEP (entrega) ===")
        by_cep: dict[str, list[dict]] = {}
        for cep in CAMPINAS_CEPS:
            payload = client.get(
                f"{base}/filial/1/loja/centros_distribuicoes/cep/{cep}/entrega", headers=hdr
            ).json()
            cds = [summarize_store(raw) for raw in (payload.get("data") or [])]
            by_cep[cep] = cds
            print(f"  cep {cep}: " + (", ".join(f"cd {cd['id']} {cd['nome']}" for cd in cds) or "—"))
        evidence["por_cep"] = by_cep

        campinas = {
            store["id"]: store
            for store in stores
            if str(store.get("cidade") or "").strip().casefold().startswith("campinas")
        }
        print(f"\n=== unidades em Campinas: {len(campinas)} ===")
        for store in campinas.values():
            print(f"  cd {store['id']}  {store['nome']}  ({store['bairro']}, cep {store['cep']})")
        evidence["campinas"] = list(campinas.values())

        # ------------------------------------------------------------- prices
        print("\n=== preços de um mesmo item por loja ===")
        terms = [term.strip().casefold() for term in args.compare.split(",") if term.strip()]
        per_store: dict[object, dict[str, dict]] = {}
        errors: dict[object, str] = {}
        for cd in list(campinas)[:8]:
            prefix = f"{base}/filial/1/centro_distribuicao/{cd}"
            tree = client.get(
                f"{prefix}/loja/classificacoes_mercadologicas/departamentos/arvore", headers=hdr
            )
            if tree.status_code != 200:
                errors[cd] = f"http {tree.status_code}"
                continue
            departments = (tree.json().get("data") or [])
            found: dict[str, dict] = {}
            for department in departments:
                dept_id = department["classificacao_mercadologica_id"]
                page = client.get(
                    f"{prefix}/loja/classificacoes_mercadologicas/departamentos/{dept_id}/produtos",
                    params={"page": 1, "limit": 100},
                    headers=hdr,
                )
                if page.status_code != 200:
                    continue
                for raw in page.json().get("data") or []:
                    description = str(raw.get("descricao") or "").casefold()
                    for term in terms:
                        if term in description and term not in found:
                            offer = raw.get("oferta") or {}
                            found[term] = {
                                "produto_id": raw.get("produto_id"),
                                "descricao": raw.get("descricao"),
                                "preco": raw.get("preco"),
                                "preco_oferta": offer.get("preco_oferta"),
                                "disponivel": raw.get("disponivel"),
                                "ean": raw.get("codigo_barras"),
                            }
                if len(found) == len(terms):
                    break
            per_store[cd] = found
            print(f"  cd {cd} ({campinas[cd]['nome']}): {len(found)}/{len(terms)} itens encontrados")
            for term, item in found.items():
                print(
                    f"      {term:<10} {str(item['descricao'])[:44]:<44} "
                    f"preco={item['preco']} oferta={item['preco_oferta']} ean={item['ean']}"
                )
        if errors:
            print(f"  lojas sem catálogo: {errors}")
        evidence["precos_por_loja"] = {str(k): v for k, v in per_store.items()}

        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / "spani_stores_evidence.json"
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nevidencias -> {path}")


if __name__ == "__main__":
    main()
