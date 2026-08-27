import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.catalog.arena import ArenaCatalogClient, write_catalog
from app.catalog.assai import AssaiCatalogClient
from app.catalog.atacadao import AtacadaoCatalogClient
from app.catalog.davita import DavitaCatalogClient
from app.catalog.goodbom import GoodBomCatalogClient
from app.catalog.persistence import (
    persist_arena_catalog,
    persist_assai_catalog,
    persist_atacadao_catalog,
    persist_davita_catalog,
    persist_goodbom_catalog,
    persist_saovicente_catalog,
    persist_savegnago_catalog,
    persist_tenda_catalog,
    reclassify_catalog_departments,
)
from app.catalog.saovicente import SaoVicenteCatalogClient
from app.catalog.savegnago import SavegnagoCatalogClient
from app.catalog.tenda import TendaCatalogClient
from app.db.models import FlyerSource, Retailer, Store
from app.db.session import SessionLocal
from app.discovery.service import discover_source
from app.extraction.service import extract_flyer

GOODBOM_MONTE_MOR = (
    "https://institucional.goodbom.com.br/tabloides/index.php/goodbom-2016-monte-mor/"
)


def seed() -> None:
    with SessionLocal() as db:
        goodbom = db.scalar(select(Retailer).where(Retailer.slug == "goodbom"))
        if not goodbom:
            goodbom = Retailer(name="GoodBom", slug="goodbom")
            db.add(goodbom)
            db.flush()
        store = db.scalar(
            select(Store).where(Store.retailer_id == goodbom.id, Store.city == "Monte Mor")
        )
        if not store:
            store = Store(
                retailer_id=goodbom.id, name="GoodBom Monte Mor", city="Monte Mor", state="SP"
            )
            db.add(store)
            db.flush()
        source = db.scalar(
            select(FlyerSource).where(
                FlyerSource.store_id == store.id, FlyerSource.url == GOODBOM_MONTE_MOR
            )
        )
        if not source:
            db.add(FlyerSource(store_id=store.id, provider_type="goodbom", url=GOODBOM_MONTE_MOR))
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed")
    discover = commands.add_parser("discover")
    discover.add_argument("--source", required=True)
    commands.add_parser("discover-all")
    commands.add_parser("reclassify-catalog")
    extract = commands.add_parser("extract")
    extract.add_argument("--flyer", required=True)
    extract.add_argument("--strategy")
    extract.add_argument("--force", action="store_true")
    arena = commands.add_parser("arena-catalog")
    arena.add_argument("--output", default="artifacts/arena")
    goodbom_catalog = commands.add_parser("goodbom-catalog")
    goodbom_catalog.add_argument("--output", default="artifacts/goodbom-catalog")
    atacadao_catalog = commands.add_parser("atacadao-catalog")
    atacadao_catalog.add_argument("--output", default="artifacts/atacadao-catalog")
    savegnago_catalog = commands.add_parser("savegnago-catalog")
    savegnago_catalog.add_argument("--output", default="artifacts/savegnago-catalog")
    davita_catalog = commands.add_parser("davitta-catalog")
    davita_catalog.add_argument("--output", default="artifacts/davitta-catalog")
    assai_catalog = commands.add_parser("assai-catalog")
    assai_catalog.add_argument("--output", default="artifacts/assai-catalog")
    tenda_catalog = commands.add_parser("tenda-catalog")
    tenda_catalog.add_argument("--output", default="artifacts/tenda-catalog")
    saovicente_catalog = commands.add_parser("saovicente-catalog")
    saovicente_catalog.add_argument("--output", default="artifacts/saovicente-catalog")
    args = parser.parse_args()
    if args.command == "seed":
        seed()
        return
    if args.command == "reclassify-catalog":
        with SessionLocal() as db:
            changed = reclassify_catalog_departments(db)
        print(f"Reclassified {changed} catalog products")
        return
    if args.command == "arena-catalog":
        catalog = asyncio.run(ArenaCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output))
        with SessionLocal() as db:
            run = persist_arena_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique products")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "goodbom-catalog":
        catalog = asyncio.run(GoodBomCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="goodbom")
        with SessionLocal() as db:
            run = persist_goodbom_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique products")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "atacadao-catalog":
        catalog = asyncio.run(AtacadaoCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="atacadao")
        with SessionLocal() as db:
            run = persist_atacadao_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique SKUs")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "savegnago-catalog":
        catalog = asyncio.run(SavegnagoCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="savegnago")
        with SessionLocal() as db:
            run = persist_savegnago_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique SKUs")
        print(f"Weekly offers: {catalog['weekly_offer_count']}")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "davitta-catalog":
        catalog = asyncio.run(DavitaCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="davitta")
        with SessionLocal() as db:
            run = persist_davita_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} Davitta promotions")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "assai-catalog":
        catalog = asyncio.run(AssaiCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="assai")
        with SessionLocal() as db:
            run = persist_assai_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} Assai authenticated promotions")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "tenda-catalog":
        catalog = asyncio.run(TendaCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="tenda")
        with SessionLocal() as db:
            run = persist_tenda_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique Tenda products")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    if args.command == "saovicente-catalog":
        catalog = asyncio.run(SaoVicenteCatalogClient().collect())
        json_path, csv_path = write_catalog(catalog, Path(args.output), prefix="sao-vicente")
        with SessionLocal() as db:
            run = persist_saovicente_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique São Vicente products")
        print(f"Persisted catalog run {run.id} at {run.collected_at.isoformat()}")
        print(json_path)
        print(csv_path)
        return
    with SessionLocal() as db:
        if args.command == "discover":
            asyncio.run(discover_source(db, UUID(args.source)))
            return
        if args.command == "discover-all":
            for source_id in db.scalars(select(FlyerSource.id).where(FlyerSource.active)).all():
                asyncio.run(discover_source(db, source_id))
            return
        asyncio.run(extract_flyer(db, UUID(args.flyer), args.force, args.strategy))


if __name__ == "__main__":
    main()
