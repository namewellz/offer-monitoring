from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from redis import Redis
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.annotation.routes import router as annotation_router
from app.catalog.dashboard import RETAILERS, render_catalog_dashboard
from app.catalog.taxonomy import CANONICAL_DEPARTMENTS
from app.catalog.update_dashboard import render_update_dashboard
from app.catalog.v2.read import (
    count_current_listings as v2_count_current_listings,
)
from app.catalog.v2.read import (
    current_listings as v2_current_listings,
)
from app.catalog.v2.read import (
    department_counts as v2_department_counts,
)
from app.catalog.v2.read import (
    latest_runs as v2_latest_runs,
)
from app.catalog.v2.read import (
    price_history_results as v2_price_history_results,
)
from app.catalog.v2.read import (
    price_results as v2_price_results,
)
from app.catalog.v2.read import (
    row_result as v2_row_result,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import (
    CatalogPriceObservation,
    CatalogProduct,
    CatalogRun,
    DiscoveryRun,
    ExtractionRun,
    Flyer,
    FlyerPage,
    FlyerSource,
    OfferPackage,
    OfferPrice,
    ProductOffer,
    Retailer,
    RunStatus,
    Store,
)
from app.db.session import get_db
from app.enrichment.butcher import butcher_comparison
from app.enrichment.dashboard import render_butcher_dashboard
from app.enrichment.review import butcher_review
from app.enrichment.review_dashboard import render_butcher_review
from app.extraction.ollama_client import OllamaVisionClient
from app.jobs.queue import (
    catalog_collection_job,
    enqueue_catalog_collection,
    enqueue_discovery,
    get_queue,
    recent_catalog_collection_jobs,
)
from app.jobs.tasks import CATALOG_COLLECTORS

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Offer Monitoring", version="0.1.0", lifespan=lifespan)
app.include_router(annotation_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def latest_catalog_run_ids():
    ranked = (
        select(
            CatalogRun.id.label("run_id"),
            func.row_number()
            .over(
                partition_by=(CatalogRun.retailer_id, CatalogRun.store_id),
                order_by=CatalogRun.collected_at.desc(),
            )
            .label("position"),
        )
        .where(CatalogRun.status == RunStatus.SUCCESS)
        .subquery()
    )
    return select(ranked.c.run_id).where(ranked.c.position == 1)


def catalog_price_condition(tier_prices: list | None) -> tuple[str, str]:
    wholesale_tiers = [
        tier
        for tier in (tier_prices or [])
        if tier.get("condition") == "wholesale" and tier.get("price") is not None
    ]
    club_tiers = [
        tier
        for tier in (tier_prices or [])
        if tier.get("condition") == "club" and tier.get("price") is not None
    ]
    app_tiers = [
        tier
        for tier in (tier_prices or [])
        if tier.get("condition") == "app" and tier.get("price") is not None
    ]
    quantity_tiers = sorted(
        (
            tier
            for tier in (tier_prices or [])
            if tier.get("minimum_quantity") is not None
            and int(tier["minimum_quantity"]) > 1
            and tier.get("condition", "quantity") == "quantity"
        ),
        key=lambda tier: (int(tier["minimum_quantity"]), float(tier.get("price") or 0)),
    )
    if not wholesale_tiers and not club_tiers and not app_tiers and not quantity_tiers:
        return "Preço final", "final"
    descriptions = [
        f"Clube/Connect: R$ {format(float(tier['price']), '.2f').replace('.', ',')}"
        for tier in club_tiers
    ]
    descriptions[0:0] = [
        f"Atacado: R$ {format(float(tier['price']), '.2f').replace('.', ',')}"
        for tier in wholesale_tiers
    ]
    descriptions.extend(
        f"App a partir de {int(tier.get('minimum_quantity') or 1)} un.: "
        f"R$ {format(float(tier['price']), '.2f').replace('.', ',')}"
        for tier in app_tiers
    )
    descriptions.extend(
        f"A partir de {int(tier['minimum_quantity'])} un.: "
        f"R$ {format(float(tier['price']), '.2f').replace('.', ',')}"
        for tier in quantity_tiers
        if tier.get("price") is not None
    )
    condition_types = [
        name
        for name, values in (
            ("wholesale", wholesale_tiers),
            ("club", club_tiers),
            ("app", app_tiers),
            ("quantity", quantity_tiers),
        )
        if values
    ]
    if len(condition_types) > 1:
        return ("Preço condicionado — " + " · ".join(descriptions), "+".join(condition_types))
    if wholesale_tiers:
        return ("Preço atacado — " + " · ".join(descriptions), "wholesale")
    if club_tiers:
        return ("Preço Clube/Connect — " + " · ".join(descriptions), "club")
    if app_tiers:
        return ("Preço exclusivo no App — " + " · ".join(descriptions), "app")
    return ("Por quantidade — " + " · ".join(descriptions), "quantity")


def catalog_price_query(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    include_unchanged: bool = False,
    offers_only: bool = False,
):
    query = (
        select(
            CatalogPriceObservation,
            CatalogProduct,
            CatalogRun,
            Retailer,
            Store,
        )
        .join(CatalogProduct, CatalogPriceObservation.product_id == CatalogProduct.id)
        .join(CatalogRun, CatalogPriceObservation.run_id == CatalogRun.id)
        .join(Retailer, CatalogRun.retailer_id == Retailer.id)
        .outerjoin(Store, CatalogPriceObservation.store_id == Store.id)
        .where(CatalogPriceObservation.run_id.in_(latest_catalog_run_ids()))
    )
    if not include_unchanged:
        query = query.where(
            CatalogPriceObservation.price_change_percent.is_not(None),
            CatalogPriceObservation.price_change_percent != 0,
            func.abs(CatalogPriceObservation.price_change_percent) >= minimum_percent,
        )
    elif minimum_percent > 0:
        query = query.where(
            CatalogPriceObservation.price_change_percent.is_not(None),
            func.abs(CatalogPriceObservation.price_change_percent) >= minimum_percent,
        )
    if offers_only:
        query = query.where(
            CatalogPriceObservation.available.is_(True),
            CatalogPriceObservation.sales_price.is_not(None),
            or_(
                CatalogPriceObservation.regular_price
                > CatalogPriceObservation.sales_price,
                CatalogPriceObservation.discount > 0,
                func.jsonb_array_length(CatalogPriceObservation.tier_prices) > 0,
                CatalogPriceObservation.offer_tags.contains(["promotion"]),
                CatalogPriceObservation.offer_tags.contains(["weekly-offers"]),
            ),
        )
    if product:
        query = query.where(CatalogProduct.name.ilike(f"%{product}%"))
    if retailer:
        query = query.where(Retailer.slug == retailer)
    if department:
        if department not in CANONICAL_DEPARTMENTS:
            raise HTTPException(400, "unknown department")
        query = query.where(CatalogProduct.department == department)
    if direction == "up":
        query = query.where(CatalogPriceObservation.price_change_percent > 0)
    elif direction == "down":
        query = query.where(CatalogPriceObservation.price_change_percent < 0)
    elif direction != "all":
        raise HTTPException(400, "direction must be all, up or down")
    return query


def catalog_price_result_count(
    db: Session,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    include_unchanged: bool = False,
    offers_only: bool = False,
) -> int:
    query = catalog_price_query(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        include_unchanged=include_unchanged,
        offers_only=offers_only,
    )
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def catalog_price_change_results(
    db: Session,
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    limit: int = 200,
    offset: int = 0,
    include_unchanged: bool = False,
    offers_only: bool = False,
) -> list[dict]:
    query = catalog_price_query(
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        include_unchanged=include_unchanged,
        offers_only=offers_only,
    )
    ordering = (
        (
            CatalogPriceObservation.discount.desc().nulls_last(),
            CatalogProduct.name,
        )
        if offers_only
        else (
            func.abs(CatalogPriceObservation.price_change_percent).desc().nulls_last(),
            CatalogProduct.name,
        )
    )
    rows = db.execute(
        query.order_by(*ordering)
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 1000))
    ).all()
    results = []
    for observation, catalog_product, run, catalog_retailer, catalog_store in rows:
        percent = observation.price_change_percent
        trend = (
            "sem referência anterior"
            if percent is None
            else "mais caro"
            if percent > 0
            else "mais barato"
            if percent < 0
            else "sem alteração"
        )
        results.append(
            {
                "product_id": catalog_product.id,
                "external_id": catalog_product.external_id,
                "ean": catalog_product.ean,
                "product": catalog_product.name,
                "brand": catalog_product.brand,
                "department": catalog_product.department,
                "source_categories": catalog_product.categories,
                "retailer": catalog_retailer.name,
                "retailer_slug": catalog_retailer.slug,
                "store": catalog_store.name if catalog_store else None,
                "observed_at": observation.observed_at,
                "previous_price": observation.previous_sales_price,
                "regular_price": observation.regular_price,
                "current_price": observation.sales_price,
                "discount": observation.discount,
                "change_amount": observation.price_change_amount,
                "change_percent": percent,
                "offer_tags": observation.offer_tags,
                "tier_prices": observation.tier_prices,
                "price_condition": catalog_price_condition(observation.tier_prices)[0],
                "price_condition_type": catalog_price_condition(observation.tier_prices)[1],
                "trend": trend,
                "summary": (
                    f"{catalog_product.name}: {abs(percent):.2f}% {trend}"
                    if percent is not None
                    else f"{catalog_product.name}: {trend}"
                ),
                "run_id": run.id,
            }
        )
    return results


def catalog_price_history_results(
    db: Session,
    product_id: str | None = None,
    ean: str | None = None,
    retailer: str | None = None,
    limit: int = 500,
) -> list[dict]:
    if not product_id and not ean:
        raise HTTPException(400, "product_id or ean is required")
    query = (
        select(
            CatalogPriceObservation,
            CatalogProduct,
            CatalogRun,
            Retailer,
            Store,
        )
        .join(CatalogProduct, CatalogPriceObservation.product_id == CatalogProduct.id)
        .join(CatalogRun, CatalogPriceObservation.run_id == CatalogRun.id)
        .join(Retailer, CatalogRun.retailer_id == Retailer.id)
        .outerjoin(Store, CatalogPriceObservation.store_id == Store.id)
    )
    if product_id:
        query = query.where(CatalogProduct.id == product_id)
    if ean:
        query = query.where(CatalogProduct.ean == ean)
    if retailer:
        query = query.where(Retailer.slug == retailer)
    rows = db.execute(
        query.order_by(CatalogPriceObservation.observed_at.desc()).limit(
            min(max(limit, 1), 5000)
        )
    ).all()
    return [
        {
            "product_id": catalog_product.id,
            "external_id": catalog_product.external_id,
            "ean": catalog_product.ean,
            "product": catalog_product.name,
            "department": catalog_product.department,
            "source_categories": catalog_product.categories,
            "retailer": catalog_retailer.name,
            "retailer_slug": catalog_retailer.slug,
            "store": catalog_store.name if catalog_store else None,
            "run_id": run.id,
            "run_status": run.status,
            "observed_at": observation.observed_at,
            "available": observation.available,
            "regular_price": observation.regular_price,
            "sales_price": observation.sales_price,
            "previous_price": observation.previous_sales_price,
            "change_amount": observation.price_change_amount,
            "change_percent": observation.price_change_percent,
            "offer_tags": observation.offer_tags,
        }
        for observation, catalog_product, run, catalog_retailer, catalog_store in rows
    ]


def item_or_404(item, name: str):
    if item is None:
        raise HTTPException(404, f"{name} not found")
    return item


def offer_results(
    db: Session,
    product: str | None = None,
    flyer_id: str | None = None,
    brand: str | None = None,
    department: str | None = None,
) -> list[dict]:
    query = (
        select(ProductOffer, Flyer, FlyerPage, Store, Retailer)
        .join(Flyer, ProductOffer.flyer_id == Flyer.id)
        .join(FlyerPage, ProductOffer.page_id == FlyerPage.id)
        .join(Store, Flyer.store_id == Store.id)
        .join(Retailer, Store.retailer_id == Retailer.id)
        .join(ExtractionRun, ProductOffer.extraction_run_id == ExtractionRun.id)
        .where(ExtractionRun.preferred.is_(True))
    )
    if product:
        query = query.where(ProductOffer.raw_name.ilike(f"%{product}%"))
    if flyer_id:
        query = query.where(ProductOffer.flyer_id == flyer_id)
    if brand:
        query = query.where(ProductOffer.brand.ilike(f"%{brand}%"))
    if department:
        if department not in CANONICAL_DEPARTMENTS:
            raise HTTPException(400, "unknown department")
        query = query.where(ProductOffer.category == department)
    rows = db.execute(query.order_by(ProductOffer.created_at.desc()).limit(500)).all()
    results = []
    for item, flyer, page, store, retailer in rows:
        prices = db.scalars(select(OfferPrice).where(OfferPrice.offer_id == item.id)).all()
        unit_price = next((price for price in prices if price.type == "UNIT_PRICE"), None)
        conditional = next(
            (
                price
                for price in prices
                if price.type == "MIN_QUANTITY"
                and price.minimum_quantity
                and not (
                    unit_price
                    and price.price == unit_price.price
                    and not (price.description or "").strip()
                )
            ),
            None,
        )
        from_to = next((price for price in prices if price.type == "FROM_TO"), None)
        fallback = next(
            (price for price in prices if price.price is not None), None
        )
        if conditional:
            normal_price = unit_price.price if unit_price else conditional.previous_price
            offer_price = conditional.price
        elif from_to and from_to.previous_price is not None:
            normal_price = from_to.previous_price
            offer_price = from_to.price
        else:
            normal_price = (unit_price or fallback).price if (unit_price or fallback) else None
            offer_price = None
        results.append(
            {
                "id": item.id,
                "product": item.normalized_name or item.raw_name,
                "department": item.category or "Outros",
                "price": normal_price,
                "offer_price": offer_price,
                "minimum_quantity": conditional.minimum_quantity if conditional else None,
                "supermarket": retailer.name,
                "store": store.name,
                "city": store.city,
                "valid_from": flyer.valid_from,
                "valid_until": flyer.valid_until,
                "source_image": f"/pages/{page.id}/image",
                "original_image_url": page.source_url,
            }
        )
    return results


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(product: str | None = None, db: Session = Depends(get_db)):
    results = offer_results(db, product)
    rows = []
    for result in results:
        price = result["price"]
        offer_price = result["offer_price"]
        if offer_price is not None:
            regular = f"R$ {price:.2f}".replace(".", ",") if price is not None else ""
            offer = f"R$ {offer_price:.2f}".replace(".", ",")
            price_text = f"{regular} → {offer}" if regular else offer
        else:
            price_text = f"R$ {price:.2f}".replace(".", ",") if price is not None else "—"
        if result["minimum_quantity"]:
            price_text += f" (mín. {result['minimum_quantity']} un.)"
        validity = " — ".join(
            value.strftime("%d/%m/%Y") if value else "?"
            for value in (result["valid_from"], result["valid_until"])
        )
        rows.append(
            "<tr>"
            f"<td><a href=\"{result['source_image']}\" target=\"_blank\">{escape(result['product'])}</a></td>"
            f"<td>{escape(price_text)}</td>"
            f"<td>{escape(result['supermarket'])}</td>"
            f"<td>{escape(result['store'])} — {escape(result['city'])}</td>"
            f"<td>{validity}</td>"
            "</tr>"
        )
    empty = '<tr><td colspan="5">Nenhuma oferta extraída ainda.</td></tr>'
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Ofertas monitoradas</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#17202a}}
main{{max-width:1200px;margin:40px auto;padding:0 20px}}h1{{margin-bottom:8px}}
form{{display:flex;gap:8px;margin:24px 0}}input{{flex:1;padding:12px;border:1px solid #ccd1d7;border-radius:8px}}
button{{padding:12px 18px;border:0;border-radius:8px;background:#176b47;color:white;cursor:pointer}}
.table{{overflow:auto;background:white;border-radius:12px;box-shadow:0 2px 12px #0000000d}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:14px;text-align:left;border-bottom:1px solid #edf0f2}}
th{{background:#eef7f2;white-space:nowrap}}small{{color:#607080}}
</style></head><body><main><h1>Ofertas monitoradas</h1>
<small>{len(results)} oferta(s) da extração mais recente de cada encarte · <a href="/annotation">Revisar marcações</a> · <a href="/catalog">Variações de preço</a></small>
<form><input name="product" value="{escape(product or '')}" placeholder="Buscar produto"><button>Buscar</button></form>
<div class="table"><table><thead><tr><th>Produto</th><th>Preço</th><th>Supermercado</th><th>Loja</th><th>Validade</th></tr></thead>
<tbody>{''.join(rows) or empty}</tbody></table></div></main></body></html>"""


@app.get("/offer-results")
def offer_results_api(
    product: str | None = None,
    department: str | None = None,
    db: Session = Depends(get_db),
):
    return offer_results(db, product, department=department)


@app.get("/catalog/price-changes")
def catalog_price_changes(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    return catalog_price_change_results(
        db,
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        limit=limit,
    )


@app.get("/catalog/departments")
def catalog_departments(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(CatalogProduct.department, func.count(func.distinct(CatalogProduct.id)))
            .join(
                CatalogPriceObservation,
                CatalogPriceObservation.product_id == CatalogProduct.id,
            )
            .where(CatalogPriceObservation.run_id.in_(latest_catalog_run_ids()))
            .group_by(CatalogProduct.department)
        ).all()
    )
    return [
        {"name": department, "product_count": counts.get(department, 0)}
        for department in CANONICAL_DEPARTMENTS
    ]


@app.get("/catalog/prices")
def catalog_prices(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    return catalog_price_change_results(
        db,
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        limit=limit,
        include_unchanged=True,
    )


@app.get("/catalog/offers")
def catalog_offers(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return catalog_price_change_results(
        db,
        product=product,
        retailer=retailer,
        department=department,
        limit=limit,
        offset=offset,
        include_unchanged=True,
        offers_only=True,
    )


@app.get("/catalog/price-history")
def catalog_price_history(
    product_id: str | None = None,
    ean: str | None = None,
    retailer: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    return catalog_price_history_results(
        db,
        product_id=product_id,
        ean=ean,
        retailer=retailer,
        limit=limit,
    )


@app.get("/catalog/v2/price-changes")
def v2_catalog_price_changes(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    try:
        return v2_price_results(
            db,
            product=product,
            retailer=retailer,
            department=department,
            direction=direction,
            minimum_percent=minimum_percent,
            view="changes",
        )[: min(max(limit, 1), 1000)]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/catalog/v2/prices")
def v2_catalog_prices(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    fast = department is None and direction == "all" and minimum_percent == 0
    if fast:
        rows = v2_current_listings(
            db,
            product=product,
            retailer=retailer,
            limit=min(max(limit, 1), 1000),
            offset=max(offset, 0),
        )
        return [v2_row_result(row) for row in rows]
    try:
        results = v2_price_results(
            db,
            product=product,
            retailer=retailer,
            department=department,
            direction=direction,
            minimum_percent=minimum_percent,
            view="all",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return results[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 1000)]


@app.get("/catalog/v2/offers")
def v2_catalog_offers(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    results = v2_price_results(
        db,
        product=product,
        retailer=retailer,
        department=department,
        view="offers",
    )
    return results[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 1000)]


@app.get("/catalog/v2/price-history")
def v2_catalog_price_history(
    product_id: int | None = None,
    ean: str | None = None,
    retailer: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    try:
        return v2_price_history_results(
            db,
            product_id=product_id,
            ean=ean,
            retailer=retailer,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/catalog/v2/departments")
def v2_catalog_departments(db: Session = Depends(get_db)):
    counts = v2_department_counts(db)
    return [
        {"name": department, "product_count": counts.get(department, 0)}
        for department in CANONICAL_DEPARTMENTS
    ]


@app.get("/catalog/cuts", response_class=HTMLResponse, include_in_schema=False)
def butcher_dashboard(limit: int = 300, all: int = 0, db: Session = Depends(get_db)):
    return render_butcher_dashboard(
        butcher_comparison(db, limit=min(max(limit, 1), 2000), use_llm=all == 0)
    )


@app.get("/catalog/cuts.json")
def butcher_json(limit: int = 300, all: int = 0, db: Session = Depends(get_db)):
    result = butcher_comparison(
        db, limit=min(max(limit, 1), 2000), use_llm=all == 0
    )
    groups = []
    for group in result["groups"]:
        groups.append(
            {
                "category": group.get("llm_category"),
                "form": group.get("form"),
                "label": group.get("label"),
                "conservation": group.get("conservation"),
                "sources": {
                    slug: {
                        "price_kg": float(info["price_kg"])
                        if info.get("price_kg") is not None
                        else None,
                        "sample": info.get("sample"),
                    }
                    for slug, info in group["sources"].items()
                },
            }
        )
    return {
        "total_items": result["total_items"],
        "total_groups": result["total_groups"],
        "llm": result.get("llm"),
        "groups": groups,
    }


@app.get("/catalog/butcher-review", response_class=HTMLResponse, include_in_schema=False)
def butcher_review_page(db: Session = Depends(get_db)):
    """Açougue classification review screen (server-rendered, live from v2)."""
    return render_butcher_review(butcher_review(db))


@app.get("/catalog/butcher-review.json")
def butcher_review_json(db: Session = Depends(get_db)):
    """JSON payload behind the review screen (same shape as the exported file)."""
    return butcher_review(db)


@app.post("/catalog/collections", status_code=202)
def request_all_catalog_collections():
    jobs = [
        {
            "job_id": enqueue_catalog_collection(retailer_slug),
            "retailer": retailer_slug,
        }
        for retailer_slug in CATALOG_COLLECTORS
    ]
    return {"jobs": jobs, "total": len(jobs)}


@app.post("/catalog/collections/{retailer_slug}", status_code=202)
def request_catalog_collection(retailer_slug: str):
    if retailer_slug not in CATALOG_COLLECTORS:
        raise HTTPException(404, "Supermercado não configurado para coleta")
    return {"job_id": enqueue_catalog_collection(retailer_slug), "retailer": retailer_slug}


@app.get("/catalog/collections/jobs/{job_id}")
def catalog_collection_status(job_id: str):
    job = catalog_collection_job(job_id)
    if job is None:
        raise HTTPException(404, "Atualização não encontrada")
    return job


@app.get("/catalog/collections/jobs")
def catalog_collection_history(limit: int = 20):
    return {"jobs": recent_catalog_collection_jobs(limit)}


def catalog_update_log_results(db: Session, executions_per_source: int = 10) -> list[dict]:
    rows = db.execute(
        select(CatalogRun, Retailer)
        .join(Retailer, Retailer.id == CatalogRun.retailer_id)
        .order_by(CatalogRun.collected_at.desc())
        .limit(300)
    ).all()
    runs_by_id = {str(run.id): run for run, _ in rows}
    groups = {
        slug: {
            "slug": slug,
            "name": name,
            "latest_product_count": 0,
            "latest_priced_product_count": 0,
            "latest_collected_at": None,
            "executions": [],
        }
        for slug, name in RETAILERS
    }
    represented_runs: set[str] = set()
    for job in recent_catalog_collection_jobs(100):
        slug = job.get("retailer")
        if slug not in groups:
            continue
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        run_id = result.get("run_id")
        run = runs_by_id.get(run_id)
        if run_id:
            represented_runs.add(run_id)
        errors = list(job.get("warnings") or [])
        if job.get("error"):
            errors.append({"scope": "coleta", "error": job["error"]})
        groups[slug]["executions"].append(
            {
                "status": job.get("outcome") or str(job.get("status") or "").upper(),
                "occurred_at": job.get("ended_at")
                or job.get("started_at")
                or job.get("enqueued_at"),
                "product_count": run.product_count if run else None,
                "priced_product_count": run.priced_product_count if run else None,
                "errors": errors,
            }
        )

    for run, retailer in rows:
        group = groups.get(retailer.slug)
        if group is None:
            continue
        if group["latest_collected_at"] is None:
            group["latest_product_count"] = run.product_count
            group["latest_priced_product_count"] = run.priced_product_count
            group["latest_collected_at"] = run.collected_at
        if str(run.id) in represented_runs:
            continue
        context = run.source_context or {}
        group["executions"].append(
            {
                "status": run.status.value,
                "occurred_at": run.collected_at,
                "product_count": run.product_count,
                "priced_product_count": run.priced_product_count,
                "errors": context.get("collection_errors") or [],
            }
        )

    for group in groups.values():
        for execution in group["executions"]:
            occurred_at = execution["occurred_at"]
            if isinstance(occurred_at, str):
                execution["occurred_at"] = datetime.fromisoformat(occurred_at)
        group["executions"].sort(
            key=lambda execution: execution["occurred_at"] or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        group["executions"] = group["executions"][:executions_per_source]
    return list(groups.values())


@app.get("/catalog/updates", response_class=HTMLResponse, include_in_schema=False)
def catalog_update_dashboard(db: Session = Depends(get_db)):
    return render_update_dashboard(catalog_update_log_results(db))


@app.get("/catalog", response_class=HTMLResponse, include_in_schema=False)
def catalog_dashboard(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    view: str = "all",
    page: int = 1,
    db: Session = Depends(get_db),
):
    if view not in {"all", "offers", "changes"}:
        raise HTTPException(400, "view must be all, offers or changes")
    page_size = 100
    fast_path = (
        view == "all"
        and department is None
        and direction == "all"
        and minimum_percent == 0
    )
    if fast_path:
        total_results = v2_count_current_listings(
            db, product=product, retailer=retailer
        )
        total_pages = max(1, (total_results + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        rows = v2_current_listings(
            db,
            product=product,
            retailer=retailer,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        page_results = [v2_row_result(row) for row in rows]
    else:
        results = v2_price_results(
            db,
            product=product,
            retailer=retailer,
            department=department,
            direction=direction,
            minimum_percent=minimum_percent,
            view=view,
        )
        total_results = len(results)
        total_pages = max(1, (total_results + page_size - 1) // page_size)
        page = min(max(page, 1), total_pages)
        page_results = results[(page - 1) * page_size : page * page_size]
    latest_runs = v2_latest_runs(db)
    return render_catalog_dashboard(
        results=page_results,
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        view=view,
        total_results=total_results,
        page=page,
        page_size=page_size,
        latest_runs=latest_runs,
    )


@app.get("/catalog/legacy", response_class=HTMLResponse, include_in_schema=False)
def legacy_catalog_dashboard(
    product: str | None = None,
    retailer: str | None = None,
    department: str | None = None,
    direction: str = "all",
    minimum_percent: float = 0,
    db: Session = Depends(get_db),
):
    results = catalog_price_change_results(
        db,
        product=product,
        retailer=retailer,
        department=department,
        direction=direction,
        minimum_percent=minimum_percent,
        limit=500,
    )
    rows = []
    for result in results:
        percent = result["change_percent"]
        css_class = "up" if percent > 0 else "down" if percent < 0 else "same"
        arrow = "▲" if percent > 0 else "▼" if percent < 0 else "—"
        store_name = result["store"] or "Todas as lojas"
        condition = result["price_condition"]
        condition_type = result["price_condition_type"]
        rows.append(
            f'<tr data-product="{escape(result["product"].casefold())}" '
            f'data-retailer="{escape(result["retailer"].casefold())}" '
            f'data-department="{escape(result["department"].casefold())}" '
            f'data-store="{escape(store_name.casefold())}" '
            f'data-previous="{result["previous_price"]}" '
            f'data-current="{result["current_price"]}" '
            f'data-change="{percent}" data-condition="{condition_type}" '
            f'data-observed="{result["observed_at"].isoformat()}">'
            f"<td>{escape(result['product'])}</td>"
            f"<td>{escape(result['department'])}</td>"
            f"<td>{escape(result['retailer'])}</td>"
            f"<td>{escape(store_name)}</td>"
            f"<td>R$ {result['previous_price']:.2f}</td>"
            f"<td>R$ {result['current_price']:.2f}</td>"
            f"<td>{escape(condition)}</td>"
            f'<td class="{css_class}">{arrow} {percent:+.2f}%</td>'
            f"<td>{result['observed_at'].strftime('%d/%m/%Y %H:%M')}</td>"
            "</tr>"
        )
    empty = '<tr><td colspan="9">Nenhuma alteração de preço na coleta mais recente.</td></tr>'
    department_options = "".join(
        f'<option value="{escape(value)}" {"selected" if department == value else ""}>{escape(value)}</option>'
        for value in CANONICAL_DEPARTMENTS
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Variações de preço</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#17202a}}
main{{max-width:1400px;margin:40px auto;padding:0 20px}}h1{{margin-bottom:8px}}
form{{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}}input,select{{padding:12px;border:1px solid #ccd1d7;border-radius:8px}}
input[name=product]{{flex:1;min-width:240px}}button{{padding:12px 18px;border:0;border-radius:8px;background:#176b47;color:white;cursor:pointer}}
.table{{overflow:auto;background:white;border-radius:12px;box-shadow:0 2px 12px #0000000d}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:14px;text-align:left;border-bottom:1px solid #edf0f2}}
th{{background:#eef7f2;white-space:nowrap}}th.sortable{{cursor:pointer;user-select:none}}th.sortable:hover{{background:#dcefe5}}
.sort-indicator{{font-size:12px;color:#176b47;margin-left:5px}}.condition{{min-width:190px}}
.up{{color:#b42318;font-weight:700}}.down{{color:#067647;font-weight:700}}small{{color:#607080}}
</style></head><body><main><h1>Variações de preço</h1>
<small>Comparação entre a coleta atual e a imediatamente anterior do mesmo produto e da mesma loja. Todo o histórico permanece armazenado.</small>
<form><input name="product" value="{escape(product or '')}" placeholder="Buscar produto">
<select name="department"><option value="">Todos os departamentos</option>{department_options}</select>
<select name="retailer"><option value="">Todos os supermercados</option>
<option value="arena-atacado" {'selected' if retailer == 'arena-atacado' else ''}>Arena Atacado</option>
<option value="goodbom" {'selected' if retailer == 'goodbom' else ''}>GoodBom</option>
<option value="atacadao" {'selected' if retailer == 'atacadao' else ''}>Atacadão</option>
<option value="savegnago" {'selected' if retailer == 'savegnago' else ''}>Savegnago</option>
<option value="davitta" {'selected' if retailer == 'davitta' else ''}>Davitta</option>
<option value="assai" {'selected' if retailer == 'assai' else ''}>Assaí</option>
<option value="tenda" {'selected' if retailer == 'tenda' else ''}>Tenda Atacado</option>
<option value="sao-vicente" {'selected' if retailer == 'sao-vicente' else ''}>São Vicente</option>
<option value="max-atacadista" {'selected' if retailer == 'max-atacadista' else ''}>Max Atacadista</option></select>
<select name="direction"><option value="all">Todas as variações</option>
<option value="up" {'selected' if direction == 'up' else ''}>Aumentos</option>
<option value="down" {'selected' if direction == 'down' else ''}>Reduções</option></select>
<input name="minimum_percent" type="number" min="0" step="0.1" value="{minimum_percent}" title="Variação mínima em %">
<button>Filtrar</button></form>
<small>Clique nos títulos para ordenar. Novos cliques em outras colunas acumulam prioridades.</small>
<div class="table"><table id="catalog-table"><thead><tr>
<th class="sortable" data-key="product">Produto</th><th class="sortable" data-key="department">Departamento</th><th class="sortable" data-key="retailer">Supermercado</th>
<th class="sortable" data-key="store">Loja</th><th class="sortable" data-key="previous">Anterior</th>
<th class="sortable" data-key="current">Atual</th><th class="sortable condition" data-key="condition">Condição do preço</th>
<th class="sortable" data-key="change">Variação</th><th class="sortable" data-key="observed">Coleta</th></tr></thead>
<tbody>{''.join(rows) or empty}</tbody></table></div>
<script>
const table = document.getElementById('catalog-table');
const sorting = [];
const numeric = new Set(['previous', 'current', 'change']);
for (const header of table.querySelectorAll('th.sortable')) {{
  header.addEventListener('click', () => {{
    const key = header.dataset.key;
    const existing = sorting.find(item => item.key === key);
    if (!existing) sorting.push({{key, direction: 'asc'}});
    else if (existing.direction === 'asc') existing.direction = 'desc';
    else sorting.splice(sorting.indexOf(existing), 1);
    const rows = [...table.tBodies[0].querySelectorAll('tr[data-product]')];
    rows.sort((left, right) => {{
      for (const item of sorting) {{
        let a = left.dataset[item.key] || '';
        let b = right.dataset[item.key] || '';
        if (numeric.has(item.key)) {{ a = Number(a); b = Number(b); }}
        const comparison = typeof a === 'number' ? a - b : a.localeCompare(b, 'pt-BR');
        if (comparison) return item.direction === 'asc' ? comparison : -comparison;
      }}
      return 0;
    }});
    rows.forEach(row => table.tBodies[0].appendChild(row));
    table.querySelectorAll('th.sortable').forEach(item => {{
      const sort = sorting.find(value => value.key === item.dataset.key);
      const old = item.querySelector('.sort-indicator');
      if (old) old.remove();
      item.removeAttribute('aria-sort');
      if (sort) {{
        item.setAttribute('aria-sort', sort.direction === 'asc' ? 'ascending' : 'descending');
        const marker = document.createElement('span');
        marker.className = 'sort-indicator';
        marker.textContent = `${{sorting.indexOf(sort) + 1}}${{sort.direction === 'asc' ? '▲' : '▼'}}`;
        item.appendChild(marker);
      }}
    }});
  }});
}}
</script></main></body></html>"""


@app.get("/pages/{page_id}/image", include_in_schema=False)
def page_image(page_id: str, db: Session = Depends(get_db)):
    page = item_or_404(db.get(FlyerPage, page_id), "Page")
    path = Path(page.local_path).resolve()
    storage = get_settings().flyer_storage_path.resolve()
    if not path.is_relative_to(storage) or not path.is_file():
        raise HTTPException(404, "Page image not found")
    return FileResponse(path, media_type=page.mime_type, filename=path.name)


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    database = redis = False
    try:
        db.execute(text("SELECT 1"))
        database = True
    except Exception:
        pass
    try:
        redis = Redis.from_url(get_settings().redis_url).ping()
    except Exception:
        pass
    ollama = await OllamaVisionClient().health()
    return {"application": True, "database": database, "redis": redis, "ollama": ollama}


@app.get("/retailers")
def retailers(db: Session = Depends(get_db)):
    return db.scalars(select(Retailer).order_by(Retailer.name)).all()


@app.get("/stores")
def stores(city: str | None = None, db: Session = Depends(get_db)):
    query = select(Store)
    if city:
        query = query.where(Store.city.ilike(f"%{city}%"))
    return db.scalars(query.order_by(Store.name)).all()


@app.get("/stores/{store_id}")
def store(store_id: str, db: Session = Depends(get_db)):
    return item_or_404(db.get(Store, store_id), "Store")


@app.get("/flyers")
def flyers(
    store: str | None = None,
    status: str | None = None,
    valid_at: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(Flyer)
    if store:
        query = query.where(Flyer.store_id == store)
    if status:
        query = query.where(Flyer.status == status)
    if valid_at:
        query = query.where(Flyer.valid_until >= valid_at)
    return db.scalars(query.order_by(Flyer.created_at.desc())).all()


@app.get("/flyers/{flyer_id}")
def flyer(flyer_id: str, db: Session = Depends(get_db)):
    return item_or_404(db.get(Flyer, flyer_id), "Flyer")


@app.get("/offers")
def offers(
    flyer_id: str | None = None,
    product: str | None = None,
    brand: str | None = None,
    department: str | None = None,
    db: Session = Depends(get_db),
):
    return offer_results(
        db,
        product=product,
        flyer_id=flyer_id,
        brand=brand,
        department=department,
    )


@app.get("/offers/{offer_id}")
def offer(offer_id: str, db: Session = Depends(get_db)):
    item = item_or_404(db.get(ProductOffer, offer_id), "Offer")
    packages = db.scalars(
        select(OfferPackage).where(OfferPackage.offer_id == item.id)
    ).all()
    prices = db.scalars(select(OfferPrice).where(OfferPrice.offer_id == item.id)).all()
    return {
        "offer": item,
        "packages": packages,
        "prices": prices,
    }


@app.get("/runs/discovery")
def discovery_runs(db: Session = Depends(get_db)):
    return db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc())).all()


@app.get("/runs/extraction")
def extraction_runs(db: Session = Depends(get_db)):
    return db.scalars(select(ExtractionRun).order_by(ExtractionRun.started_at.desc())).all()


@app.post("/sources/{source_id}/discover", status_code=202)
def discover(source_id: str, db: Session = Depends(get_db)):
    item_or_404(db.get(FlyerSource, source_id), "Source")
    return {"job_id": enqueue_discovery(source_id)}


@app.post("/flyers/{flyer_id}/extract", status_code=202)
def extract(flyer_id: str, db: Session = Depends(get_db)):
    item_or_404(db.get(Flyer, flyer_id), "Flyer")
    return {
        "job_id": get_queue()
        .enqueue("app.jobs.tasks.run_extraction", flyer_id, job_timeout="15m")
        .id
    }


@app.post("/flyers/{flyer_id}/reprocess", status_code=202)
def reprocess(flyer_id: str, strategy: str | None = None, db: Session = Depends(get_db)):
    item_or_404(db.get(Flyer, flyer_id), "Flyer")
    return {
        "job_id": get_queue()
        .enqueue("app.jobs.tasks.run_extraction", flyer_id, True, strategy, job_timeout="15m")
        .id
    }
