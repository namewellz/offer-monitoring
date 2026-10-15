import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.catalog.arena import ArenaCatalogClient, write_catalog
from app.catalog.assai import AssaiCatalogClient
from app.catalog.atacadao import (
    ALLOWED_FILIAIS,
    CAMPINAS_STORES,
    REGION_CITIES,
    AtacadaoCatalogClient,
)
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
    persist_spani_catalog,
    persist_savegnago_catalog,
    persist_tenda_catalog,
    reclassify_catalog_departments,
)
from app.catalog.saovicente import SaoVicenteCatalogClient
from app.catalog.savegnago import SavegnagoCatalogClient
from app.catalog.tenda import TendaCatalogClient
from app.catalog.v2.backfill import backfill_v2
from app.catalog.vipcommerce import SpaniCatalogClient
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
    commands.add_parser("backfill-v2")
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
    atacadao_catalog.add_argument(
        "--region",
        choices=["campinas", "rmc"],
        default="campinas",
        help=(
            "Lojas a coletar: as lojas da regiao de Campinas (padrao) ou as lojas "
            "descobertas ao vivo na API do app, filtradas pela allowlist de Campinas."
        ),
    )
    atacadao_catalog.add_argument(
        "--filial",
        type=int,
        action="append",
        default=[],
        help="Coleta apenas as lojas (número da filial) indicadas. Repetível.",
    )
    atacadao_catalog.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Requisições simultâneas por loja (máximo 6, padrão 6).",
    )
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
    spani_catalog = commands.add_parser("spani-catalog")
    spani_catalog.add_argument("--output", default="artifacts/spani-catalog")
    spani_catalog.add_argument(
        "--region",
        choices=["campinas", "todas"],
        default="campinas",
        help=(
            "Unidades a coletar: as lojas de Campinas (padrão) ou todas as unidades "
            "da rede descobertas na API do app."
        ),
    )
    spani_catalog.add_argument(
        "--cd",
        type=int,
        action="append",
        default=[],
        help="Coleta apenas as unidades (centro de distribuição) indicadas. Repetível.",
    )
    max_catalog = commands.add_parser("max-atacadista-catalog")
    max_catalog.add_argument("--output", default="artifacts/max-atacadista-catalog")
    args = parser.parse_args()
    if args.command == "seed":
        seed()
        return
    if args.command == "reclassify-catalog":
        with SessionLocal() as db:
            changed = reclassify_catalog_departments(db)
        print(f"Reclassified {changed} catalog products")
        return
    if args.command == "backfill-v2":
        with SessionLocal() as db:
            result = backfill_v2(db)
        print("Backfilled v2 catalog model:")
        for key, value in result.items():
            print(f"  {key}: {value}")
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
        client = AtacadaoCatalogClient(concurrency=args.concurrency)
        known = {store["filial"]: store for store in CAMPINAS_STORES}
        if args.filial:
            if any(filial not in known for filial in args.filial):
                for store in asyncio.run(client.find_stores(REGION_CITIES)):
                    known.setdefault(store["filial"], store)
                unknown = [filial for filial in args.filial if filial not in known]
                if unknown:
                    raise SystemExit(f"Filial não encontrada na API do app: {unknown}")
            stores = [known[filial] for filial in args.filial]
        elif args.region == "campinas":
            stores = list(CAMPINAS_STORES)
        else:  # rmc: descoberta ao vivo, mas so filiais da allowlist
            found = asyncio.run(client.find_stores(REGION_CITIES))
            skipped = [s["filial"] for s in found if s["filial"] not in ALLOWED_FILIAIS]
            if skipped:
                print(f"ignorando filiais fora da allowlist de Campinas: {skipped}")
            stores = [s for s in found if s["filial"] in ALLOWED_FILIAIS]
        catalogs = asyncio.run(client.collect_many(stores))
        total_skus = 0
        total_priced = 0
        total_available = 0
        total_offers = 0
        with SessionLocal() as db:
            for index, catalog in enumerate(catalogs):
                prefix = f"atacadao-{index:02d}"
                json_path, csv_path = write_catalog(catalog, Path(args.output), prefix=prefix)
                run = persist_atacadao_catalog(db, catalog)
                priced = sum(
                    1 for product in catalog["products"] if product.get("sales_price") is not None
                )
                available = sum(1 for product in catalog["products"] if product.get("available"))
                offers = sum(
                    1 for product in catalog["products"] if product.get("tier_prices")
                )
                total_skus += len(catalog["products"])
                total_priced += priced
                total_available += available
                total_offers += offers
                print(
                    f"[{catalog['store']['name']} filial {catalog['store']['filial']}] "
                    f"{len(catalog['products'])} SKUs, {priced} com preço, "
                    f"{available} disponíveis, {offers} com oferta app/cartão -> run {run.id}"
                )
                print(json_path)
                print(csv_path)
        print(
            f"TOTAL {len(catalogs)} lojas: {total_skus} SKUs, "
            f"{total_priced} com preço, {total_available} disponíveis, "
            f"{total_offers} com oferta app/cartão"
        )
        return
    if args.command == "spani-catalog":
        client = SpaniCatalogClient()
        if args.cd:
            known = {
                unit["centro_distribuicao"]: unit
                for unit in asyncio.run(client.list_centros_distribuicao())
            }
            missing = [cd for cd in args.cd if str(cd) not in known]
            if missing:
                raise SystemExit(f"Centro de distribuição não encontrado: {missing}")
            units = [known[str(cd)] for cd in args.cd]
        elif args.region == "campinas":
            units = asyncio.run(client.units_for_city("Campinas"))
        else:
            units = asyncio.run(client.list_centros_distribuicao())
        catalogs = asyncio.run(client.collect_many(units))
        total_skus = 0
        total_priced = 0
        total_offers = 0
        with SessionLocal() as db:
            for index, catalog in enumerate(catalogs):
                json_path, csv_path = write_catalog(
                    catalog, Path(args.output), prefix=f"spani-{index:02d}"
                )
                run = persist_spani_catalog(db, catalog)
                priced = sum(
                    1 for product in catalog["products"] if product.get("sales_price") is not None
                )
                offers = sum(1 for product in catalog["products"] if product.get("offer_tags"))
                total_skus += len(catalog["products"])
                total_priced += priced
                total_offers += offers
                print(
                    f"[{catalog['store']['name']} cd "
                    f"{catalog['store']['centro_distribuicao']}] {len(catalog['products'])} SKUs, "
                    f"{priced} com preço, {offers} em oferta -> run {run.id}"
                )
                print(json_path)
                print(csv_path)
        print(
            f"TOTAL {len(catalogs)} lojas: {total_skus} SKUs, {total_priced} com preço, "
            f"{total_offers} em oferta"
        )
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
    if args.command == "max-atacadista-catalog":
        catalog = asyncio.run(MaxAtacadistaCatalogClient().collect())
        json_path, csv_path = write_catalog(
            catalog, Path(args.output), prefix="max-atacadista"
        )
        with SessionLocal() as db:
            run = persist_maxatacadista_catalog(db, catalog)
        print(f"Collected {catalog['product_count']} unique Max Atacadista products")
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
