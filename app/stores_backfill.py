"""Backfill de metadados de lojas (python -m app.stores_backfill [--dry-run]).

Ordem/precedencia: manual > fonte do varejista (app Atacadao) > ViaCEP > vazio.
Campos ja marcados ``manual`` em ``field_sources`` nao sao sobrescritos.
Divergencias viram ``field_sources.conflicts`` e entram na lista de revisao
(docs/stores/review_list.json quando rodado no repo; impresso no stdout).
Nada de chute: bairro sem fonte confiavel fica NULL com ``curation=a_confirmar``.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Any

import httpx
from sqlalchemy import select

from app.db.models import Retailer, Store
from app.db.session import SessionLocal
from app.stores import fold, refresh_store_labels

CAMPINAS_REGION_CITIES = {
    fold(c)
    for c in (
        "Campinas", "Hortolândia", "Sumaré", "Americana", "Indaiatuba", "Itu", "Jundiaí",
        "Santa Bárbara d'Oeste", "Monte Mor", "Valinhos", "Vinhedo", "Paulínia",
        "Nova Odessa", "Jaguariúna", "Cosmópolis", "Artur Nogueira", "Itatiba",
    )
}
# CEP de referencia (centro de Hortolandia) usado por varios coletores: nao e CEP de loja.
REFERENCE_CEPS = {"13184222"}
# CEP real por loja quando o coletor so tem referencia (Savegnago: endereco da loja bate).
REAL_CEP_BY_NAME = {"Hortolândia - Hortolândia - LJ 55": "13184222"}
# Codigo da loja no varejista (a partir de collection_targets/source_context ja coletados).
STORE_CODES = {
    "Assaí Hortolândia – Loja 175": "175",
    "Loja 04 – Monte Mor": "04",
    "GoodBom Hortolândia": "hortolandia",
    "GoodBom Monte Mor": "monte-mor",
    "Max Atacadista Campinas": "141",
    "Pague Menos Hortolândia (Loja 16 - Rosolen)": "16",
    "São Vicente Hortolândia": "018",
    "Hortolândia - Hortolândia - LJ 55": "55",
    "Tenda Hortolândia": "CT39",
    "Taquaral (Campinas)": "1",
    "Spani Campinas 1": "CD40",
    "Spani Campinas 2": "CD41",
    "Spani Campinas 3": "CD42",
}
# Decisao do usuario (14/10): assumir 'loja', investigar depois.
TYPE_TO_CONFIRM = {
    "Spani Campinas 1": "Spani: loja fisica ou CD de e-commerce (centro_distribuicao 40)?",
    "Spani Campinas 2": "Spani: loja fisica ou CD de e-commerce (centro_distribuicao 41)?",
    "Spani Campinas 3": "Spani: loja fisica ou CD de e-commerce (centro_distribuicao 42)?",
    "Max Atacadista Campinas": "Max: referencia regional; qual loja fisica real?",
    "GoodBom Monte Mor": "GoodBom Monte Mor: coletado com CEP de referencia de Hortolandia",
}
DISPLAY_LABELS = {
    "Atacadão Campinas Jd. Yeda": "Jd. Yeda",
    "Atacadão Campinas Dom Pedro": "Dom Pedro",
    "Atacadão Campinas Dunlop 24h": "Dunlop 24h",
}


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _cep_fmt(digits: str) -> str | None:
    return f"{digits[:5]}-{digits[5:]}" if len(digits) == 8 else None


async def _atacadao_rows(cities: set[str]) -> dict[int, dict[str, Any]]:
    from app.catalog.atacadao import BACKOFFICE, AtacadaoCatalogClient

    api = AtacadaoCatalogClient()
    found: dict[int, dict[str, Any]] = {}

    async def run(client):
        for city in sorted(cities):
            try:
                payload = await api._get(
                    client,
                    f"{BACKOFFICE}/busca-loja-via-cidade-nome/v2",
                    {"page": 1, "pageSize": 50, "cityOrName": city, "lat": 0.0, "lon": 0.0},
                )
            except Exception:  # noqa: BLE001 - fonte opcional
                continue
            for row in payload.get("data") or []:
                if row.get("idStore") is not None:
                    found[int(row["idStore"])] = row

    await api._with_client(run)
    return found


def _viacep(client: httpx.Client, digits: str) -> dict[str, Any] | None:
    try:
        response = client.get(f"https://viacep.com.br/ws/{digits}/json/")
        data = response.json()
    except Exception:  # noqa: BLE001
        return None
    return None if data.get("erro") else data


def _set(store: Store, sources: dict[str, Any], field: str, value: Any, source: str) -> None:
    if sources.get(field) == "manual":
        return
    setattr(store, field, value)
    sources[field] = source


def main(dry_run: bool = False) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    with SessionLocal() as db:
        rows = db.execute(select(Store, Retailer).join(Retailer, Retailer.id == Store.retailer_id)).all()
        from app.db.models_v2 import CollectionTarget

        targets: dict[Any, list[CollectionTarget]] = {}
        for target in db.scalars(select(CollectionTarget)).all():
            targets.setdefault(target.store_id, []).append(target)

        atacadao_cities = {
            fold(store.city) for store, retailer in rows
            if retailer.slug == "atacadao" and store.city != "Nacional"
        } | {"vila maria"}
        app_rows = asyncio.run(_atacadao_rows(atacadao_cities))
        http = httpx.Client(timeout=10, headers={"User-Agent": "offer-monitoring/0.1"})

        for store, retailer in rows:
            sources: dict[str, Any] = dict(store.field_sources or {})
            sources.pop("conflicts", None)
            todo: list[str] = []
            # 1) regras
            if store.city == "Nacional":
                _set(store, sources, "store_type", "online", "rule")
                _set(store, sources, "region_bucket", "online", "rule")
            else:
                _set(store, sources, "store_type", "loja", "rule")
                bucket = "campinas" if fold(store.city) in CAMPINAS_REGION_CITIES else "fora"
                _set(store, sources, "region_bucket", bucket, "rule")
            if store.name in TYPE_TO_CONFIRM:
                todo.append(TYPE_TO_CONFIRM[store.name])
            if store.name in DISPLAY_LABELS:
                _set(store, sources, "display_label", DISPLAY_LABELS[store.name], "rule")
            if store.name in STORE_CODES:
                _set(store, sources, "store_code", STORE_CODES[store.name], "collector")

            if store.store_type == "online":
                store.field_sources = sources
                continue

            # 2) fonte do varejista
            app_row = None
            if retailer.slug == "atacadao":
                filial = None
                for target in targets.get(store.id, []):
                    cfg = target.public_config or {}
                    filial = cfg.get("filial") or filial
                    if not filial and (target.seller_id or "").startswith("atacadaobr"):
                        filial = int(target.seller_id.removeprefix("atacadaobr"))
                if filial:
                    _set(store, sources, "store_code", str(filial), "atacadao-app")
                    app_row = app_rows.get(int(filial))
            cep = ""
            app_bairro = None
            if app_row:
                app_bairro = (app_row.get("neighborhood") or "").strip() or None
                cep = _digits(app_row.get("zipCode"))
                address = ", ".join(
                    str(p).strip() for p in (app_row.get("address"), app_row.get("number")) if p
                )
                if address:
                    _set(store, sources, "address_line", address, "atacadao-app")
                try:
                    _set(store, sources, "latitude", round(float(app_row["latitude"]), 6), "atacadao-app")
                    _set(store, sources, "longitude", round(float(app_row["longitude"]), 6), "atacadao-app")
                except (KeyError, TypeError, ValueError):
                    pass
            if not cep:
                cep = REAL_CEP_BY_NAME.get(store.name, "")
            if not cep:
                for target in targets.get(store.id, []):
                    candidate = _digits(target.reference_postal_code)
                    if len(candidate) == 8 and candidate not in REFERENCE_CEPS:
                        cep = candidate
            # 3) ViaCEP
            via = _viacep(http, cep) if len(cep) == 8 else None
            if cep:
                _set(store, sources, "postal_code", _cep_fmt(cep), "atacadao-app" if app_row else "collector")
            via_bairro = (via or {}).get("bairro") or None
            if not store.address_line and via and via.get("logradouro"):
                _set(store, sources, "address_line", via["logradouro"], "viacep")
            bairro = None
            if app_bairro and via_bairro:
                if fold(app_bairro) == fold(via_bairro):
                    bairro, src = via_bairro, "atacadao-app=viacep"  # grafia com acento
                else:
                    bairro, src = app_bairro, "atacadao-app"
                    sources["conflicts"] = {"neighborhood": {"atacadao-app": app_bairro, "viacep": via_bairro}}
                    review.append({"store": store.name, "field": "bairro", "atacadao-app": app_bairro,
                                   "viacep": via_bairro, "chosen": app_bairro})
            elif app_bairro:
                bairro, src = app_bairro, "atacadao-app"
            elif via_bairro:
                bairro, src = via_bairro, "viacep"
            if bairro:
                _set(store, sources, "neighborhood", bairro, src)
            elif sources.get("neighborhood") != "manual":
                store.neighborhood = None
                sources["neighborhood"] = "gap"
                todo.append("bairro sem fonte confiavel (CEP real desconhecido)")
            if todo:
                sources["curation"] = "a_confirmar"
                sources["curation_notes"] = todo
                review.append({"store": store.name, "field": "curation", "notes": todo})
            else:
                sources.pop("curation", None)
                sources.pop("curation_notes", None)
            store.field_sources = sources
        http.close()
        if dry_run:
            db.rollback()
        else:
            db.commit()
            refresh_store_labels(db)
    return review


if __name__ == "__main__":
    result = main(dry_run="--dry-run" in sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=1))
