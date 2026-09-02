import asyncio
from pathlib import Path
from uuid import UUID

from redis import Redis

from app.catalog.arena import ArenaCatalogClient, write_catalog
from app.catalog.assai import AssaiCatalogClient
from app.catalog.atacadao import AtacadaoCatalogClient
from app.catalog.davita import DavitaCatalogClient
from app.catalog.goodbom import GoodBomCatalogClient
from app.catalog.maxatacadista import MaxAtacadistaCatalogClient
from app.catalog.persistence import (
    persist_arena_catalog,
    persist_assai_catalog,
    persist_atacadao_catalog,
    persist_davita_catalog,
    persist_goodbom_catalog,
    persist_maxatacadista_catalog,
    persist_saovicente_catalog,
    persist_savegnago_catalog,
    persist_tenda_catalog,
)
from app.catalog.saovicente import SaoVicenteCatalogClient
from app.catalog.savegnago import SavegnagoCatalogClient
from app.catalog.tenda import TendaCatalogClient
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.discovery.service import discover_source
from app.extraction.service import extract_flyer


def _locked(name: str):
    settings = get_settings()
    return Redis.from_url(settings.redis_url).lock(
        name, timeout=settings.job_lock_timeout_seconds, blocking_timeout=1
    )


def run_discovery(source_id: str) -> str | None:
    lock = _locked(f"discovery:{source_id}")
    if not lock.acquire(blocking=True):
        return None
    try:
        with SessionLocal() as db:
            return str(asyncio.run(discover_source(db, UUID(source_id))))
    finally:
        lock.release()


def run_extraction(flyer_id: str, force: bool = False, strategy: str | None = None) -> str | None:
    lock = _locked(f"extraction:{flyer_id}")
    if not lock.acquire(blocking=True):
        return None
    try:
        with SessionLocal() as db:
            result = asyncio.run(extract_flyer(db, UUID(flyer_id), force, strategy))
            return str(result) if result else None
    finally:
        lock.release()


CATALOG_COLLECTORS = {
    "arena-atacado": (ArenaCatalogClient, persist_arena_catalog, "arena"),
    "goodbom": (GoodBomCatalogClient, persist_goodbom_catalog, "goodbom"),
    "atacadao": (AtacadaoCatalogClient, persist_atacadao_catalog, "atacadao"),
    "savegnago": (SavegnagoCatalogClient, persist_savegnago_catalog, "savegnago"),
    "davitta": (DavitaCatalogClient, persist_davita_catalog, "davitta"),
    "assai": (AssaiCatalogClient, persist_assai_catalog, "assai"),
    "tenda": (TendaCatalogClient, persist_tenda_catalog, "tenda"),
    "sao-vicente": (SaoVicenteCatalogClient, persist_saovicente_catalog, "sao-vicente"),
    "max-atacadista": (
        MaxAtacadistaCatalogClient,
        persist_maxatacadista_catalog,
        "max-atacadista",
    ),
}


def run_catalog_collection(retailer_slug: str) -> dict | None:
    if retailer_slug not in CATALOG_COLLECTORS:
        raise ValueError(f"Unknown catalog retailer: {retailer_slug}")
    lock = _locked(f"catalog:{retailer_slug}")
    if not lock.acquire(blocking=True):
        return None
    try:
        collector_type, persist, prefix = CATALOG_COLLECTORS[retailer_slug]
        catalog = asyncio.run(collector_type().collect())
        output = get_settings().flyer_storage_path / "catalog" / retailer_slug
        write_catalog(catalog, Path(output), prefix=prefix)
        with SessionLocal() as db:
            run = persist(db, catalog)
            return {
                "run_id": str(run.id),
                "status": run.status.value,
                "errors": catalog.get("collection_errors", []),
            }
    finally:
        lock.release()
