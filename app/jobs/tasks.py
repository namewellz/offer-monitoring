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
from app.catalog.paguemenos import PagueMenosCatalogClient
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
    persist_dalben_catalog,
    persist_spani_catalog,
    persist_paguemenos_catalog,
)
from app.catalog.saovicente import SaoVicenteCatalogClient
from app.catalog.savegnago import SavegnagoCatalogClient
from app.catalog.tenda import TendaCatalogClient
from app.catalog.vipcommerce import DalbenCatalogClient, SpaniCatalogClient
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
    "dalben": (DalbenCatalogClient, persist_dalben_catalog, "dalben"),
    "spani": (SpaniCatalogClient, persist_spani_catalog, "spani"),
    "pague-menos": (
        PagueMenosCatalogClient,
        persist_paguemenos_catalog,
        "pague-menos",
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
        collector = collector_type()
        # Multi-store collectors (one catalog per physical branch) advertise this;
        # single-store collectors keep the historical one-catalog behaviour.
        collect_all = getattr(collector, "collect_all", None)
        catalogs = asyncio.run(collect_all()) if callable(collect_all) else [asyncio.run(collector.collect())]
        output = get_settings().flyer_storage_path / "catalog" / retailer_slug
        run = None
        errors: list[dict] = []
        runs: list[str] = []
        for index, catalog in enumerate(catalogs):
            catalog_prefix = prefix if len(catalogs) == 1 else f"{prefix}-{index:02d}"
            write_catalog(catalog, Path(output), prefix=catalog_prefix)
            with SessionLocal() as db:
                run = persist(db, catalog)
            errors.extend(catalog.get("collection_errors", []))
            runs.append(str(run.id))
        outcome = run.status.value if run is not None else "FAILED"
        enqueue_post_collection(retailer_slug, outcome)
        return {
            "run_id": str(run.id) if run is not None else None,
            "status": outcome,
            "errors": errors,
            "stores": len(catalogs),
            "runs": runs,
        }
    finally:
        lock.release()


def enqueue_post_collection(retailer_slug: str, outcome: str) -> None:
    """After a saved collection, queue normalization and then classification.

    Each enqueue is isolated. A failure here does not roll back the collection,
    and a failure of one job does not stop the other from being queued.
    Normalization stays off unless ``canonical_enabled`` is set.
    """
    if outcome not in ("SUCCESS", "PARTIAL_SUCCESS"):
        return
    if get_settings().canonical_enabled:
        try:
            from app.jobs.queue import enqueue_normalize_new

            enqueue_normalize_new(retailer_slug)
        except Exception:
            pass
    try:
        from app.jobs.queue import enqueue_classify_new

        enqueue_classify_new(retailer_slug=retailer_slug)
    except Exception:
        pass


def run_normalize_new(retailer_slug: str) -> dict | None:
    """Normalize this retailer's new or changed product versions. No network, no LLM."""
    if retailer_slug not in CATALOG_COLLECTORS:
        raise ValueError(f"Unknown catalog retailer: {retailer_slug}")
    if not get_settings().canonical_enabled:
        return {"skipped": True, "reason": "canonical_disabled", "retailer": retailer_slug}
    lock = _locked(f"normalize:new:{retailer_slug}")
    if not lock.acquire(blocking=False):
        return None
    try:
        from app.canonical.incremental import normalize_retailer

        with SessionLocal() as db:
            return normalize_retailer(db, retailer_slug)
    finally:
        lock.release()


def run_classify_new(retailer_slug: str | None = None, max_items: int = 800) -> dict | None:
    """Classifica automaticamente produtos nunca classificados (DeepSeek)."""
    lock = _locked(f"classify:new:{retailer_slug or 'all'}")
    if not lock.acquire(blocking=False):
        return None
    try:
        from app.classification.automation import classify_new_products

        with SessionLocal() as db:
            return classify_new_products(db, retailer=retailer_slug, max_items=max_items)
    finally:
        lock.release()
