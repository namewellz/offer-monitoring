from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.db.models import (
    CatalogPriceObservation,
    CatalogProduct,
    CatalogRun,
    Retailer,
    RunStatus,
    Store,
)


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _bounded(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= maximum else None


def price_change(
    current: Decimal | None, previous: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    if current is None or previous is None or previous <= 0:
        return None, None
    amount = current - previous
    percent = (amount / previous * Decimal("100")).quantize(Decimal("0.0001"))
    return amount, percent


def reclassify_catalog_departments(db: Session) -> int:
    """Reapply the current taxonomy to products already stored in the database."""
    changed = 0
    products = db.scalars(select(CatalogProduct)).yield_per(1000)
    for product in products:
        department = canonical_department(product.categories, product.name)
        if product.department != department:
            product.department = department
            changed += 1
    db.commit()
    return changed


def _persist_catalog(
    db: Session,
    catalog: dict[str, Any],
    *,
    retailer_name: str,
    retailer_slug: str,
    provider_type: str,
    store: Store | None,
) -> CatalogRun:
    observed_at = datetime.fromisoformat(catalog["collected_at"])
    retailer = db.scalar(select(Retailer).where(Retailer.slug == retailer_slug))
    if retailer is None:
        retailer = Retailer(name=retailer_name, slug=retailer_slug)
        db.add(retailer)
        db.flush()

    existing_run = db.scalar(
        select(CatalogRun).where(
            CatalogRun.retailer_id == retailer.id,
            CatalogRun.provider_type == provider_type,
            CatalogRun.source_url == catalog["source"],
            CatalogRun.collected_at == observed_at,
        )
    )
    if existing_run is not None:
        return existing_run

    products = catalog["products"]
    run = CatalogRun(
        retailer_id=retailer.id,
        store_id=store.id if store else None,
        provider_type=provider_type,
        source_url=catalog["source"],
        status=RunStatus.SUCCESS,
        collected_at=observed_at,
        product_count=len(products),
        priced_product_count=sum(
            p.get("sales_price") is not None and float(p["sales_price"]) > 0 for p in products
        ),
        source_context={
            "department_counts": catalog.get("department_counts", {}),
            "store": catalog.get("store"),
            "weekly_offer_count": catalog.get("weekly_offer_count"),
            "promotion_count": catalog.get("promotion_count"),
        },
    )
    db.add(run)
    db.flush()

    existing_products = {
        item.external_id: item
        for item in db.scalars(
            select(CatalogProduct).where(CatalogProduct.retailer_id == retailer.id)
        ).all()
    }
    product_ids = [product.id for product in existing_products.values()]
    previous_observations = {}
    if product_ids:
        previous_query = (
            select(CatalogPriceObservation)
            .where(
                CatalogPriceObservation.product_id.in_(product_ids),
                CatalogPriceObservation.observed_at < observed_at,
            )
            .order_by(
                CatalogPriceObservation.product_id,
                CatalogPriceObservation.observed_at.desc(),
            )
            .distinct(CatalogPriceObservation.product_id)
        )
        if store is None:
            previous_query = previous_query.where(CatalogPriceObservation.store_id.is_(None))
        else:
            previous_query = previous_query.where(CatalogPriceObservation.store_id == store.id)
        previous_observations = {
            observation.product_id: observation for observation in db.scalars(previous_query).all()
        }
    for raw in products:
        source_categories = raw.get("categories") or []
        department = canonical_department(source_categories, raw["name"])
        product = existing_products.get(raw["id"])
        if product is None:
            product = CatalogProduct(
                retailer_id=retailer.id,
                external_id=raw["id"],
                name=raw["name"],
                brand=_bounded(raw.get("brand"), 160),
                categories=source_categories,
                department=department,
                measure=_bounded(raw.get("measure"), 50),
                product_url=raw.get("product_url"),
                image_url=raw.get("image_url"),
                ean=_bounded(raw.get("ean"), 32),
                internal_code=_bounded(raw.get("internal_code"), 120),
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            db.add(product)
            db.flush()
            existing_products[raw["id"]] = product
        product.name = raw["name"]
        product.brand = _bounded(raw.get("brand"), 160)
        product.categories = source_categories
        product.department = department
        product.measure = _bounded(raw.get("measure"), 50)
        product.product_url = raw.get("product_url")
        product.image_url = raw.get("image_url")
        product.ean = _bounded(raw.get("ean"), 32)
        product.internal_code = _bounded(raw.get("internal_code"), 120)
        product.last_seen_at = observed_at
        current_price = _decimal(raw.get("sales_price"))
        previous_observation = previous_observations.get(product.id)
        previous_price = (
            previous_observation.sales_price if previous_observation is not None else None
        )
        change_amount, change_percent = price_change(current_price, previous_price)
        db.add(
            CatalogPriceObservation(
                run_id=run.id,
                product_id=product.id,
                store_id=store.id if store else None,
                observed_at=observed_at,
                available=bool(raw.get("available")),
                stock=_decimal(raw.get("stock")),
                regular_price=_decimal(raw.get("regular_price")),
                sales_price=current_price,
                previous_sales_price=previous_price,
                price_change_amount=change_amount,
                price_change_percent=change_percent,
                offer_tags=raw.get("offer_tags") or [],
                discount=_decimal(raw.get("discount")),
                tier_prices=raw.get("tier_prices") or [],
            )
        )
    db.commit()
    return run


def persist_arena_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Arena Atacado",
        retailer_slug="arena-atacado",
        provider_type="arena-api",
        store=None,
    )


def persist_goodbom_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "goodbom"))
    if retailer is None:
        retailer = Retailer(name="GoodBom", slug="goodbom")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.city == store_data["city"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="GoodBom",
        retailer_slug="goodbom",
        provider_type="goodbom-api",
        store=store,
    )


def persist_atacadao_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "atacadao"))
    if retailer is None:
        retailer = Retailer(name="Atacadão", slug="atacadao")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Atacadão",
        retailer_slug="atacadao",
        provider_type="atacadao-vtex-api",
        store=store,
    )


def persist_savegnago_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "savegnago"))
    if retailer is None:
        retailer = Retailer(name="Savegnago", slug="savegnago")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Savegnago",
        retailer_slug="savegnago",
        provider_type="savegnago-vtex-api",
        store=store,
    )


def persist_davita_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "davitta"))
    if retailer is None:
        retailer = Retailer(name="Davitta Supermercados", slug="davitta")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Davitta Supermercados",
        retailer_slug="davitta",
        provider_type="davita-mobilesim-api",
        store=store,
    )


def persist_assai_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "assai"))
    if retailer is None:
        retailer = Retailer(name="Assaí Atacadista", slug="assai")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Assaí Atacadista",
        retailer_slug="assai",
        provider_type="assai-authenticated-api",
        store=store,
    )


def persist_tenda_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "tenda"))
    if retailer is None:
        retailer = Retailer(name="Tenda Atacado", slug="tenda")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="Tenda Atacado",
        retailer_slug="tenda",
        provider_type="tenda-public-api",
        store=store,
    )


def persist_saovicente_catalog(db: Session, catalog: dict[str, Any]) -> CatalogRun:
    retailer = db.scalar(select(Retailer).where(Retailer.slug == "sao-vicente"))
    if retailer is None:
        retailer = Retailer(name="São Vicente", slug="sao-vicente")
        db.add(retailer)
        db.flush()
    store_data = catalog["store"]
    store = db.scalar(
        select(Store).where(
            Store.retailer_id == retailer.id,
            Store.name == store_data["name"],
        )
    )
    if store is None:
        store = Store(
            retailer_id=retailer.id,
            name=store_data["name"],
            city=store_data["city"],
            state=store_data["state"],
        )
        db.add(store)
        db.flush()
    return _persist_catalog(
        db,
        catalog,
        retailer_name="São Vicente",
        retailer_slug="sao-vicente",
        provider_type="saovicente-demandware-api",
        store=store,
    )
