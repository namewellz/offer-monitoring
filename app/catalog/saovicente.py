from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.catalog.resilience import collection_issue, collection_metadata, require_products

SOURCE_URL = "https://www.svicente.com.br/"
BASE_URL = (
    "https://www.svicente.com.br/on/demandware.store/"
    "Sites-SaoVicente-Site/pt_BR/"
)
SEARCH_URL = f"{BASE_URL}Search-UpdateGrid"
AVAILABLE_STORES_URL = f"{BASE_URL}Stores-AvailableStores"
SELECT_STORE_URL = f"{BASE_URL}Stores-CheckStock"

STORE_ID = "018"
REFERENCE_ZIP_CODE = "13184222"
STORE = {
    "id": STORE_ID,
    "name": "São Vicente Hortolândia",
    "city": "Hortolândia",
    "state": "SP",
    "zip_code": REFERENCE_ZIP_CODE,
}

DEPARTMENTS = {
    "001": "Bazar E Utilidades",
    "002": "Bebidas",
    "003": "Bebidas Alcoólicas",
    "004": "Biscoitos E Salgadinhos",
    "005": "Carnes, Aves E Peixes",
    "006": "Congelados",
    "007": "Doces E Sobremesas",
    "008": "Frios E Laticínios",
    "009": "Higiene E Beleza",
    "010": "Hortifruti",
    "011": "Limpeza",
    "012": "Mercearia",
    "014": "Mundo Pet",
    "015": "Padaria",
    "016": "Saudáveis E Orgânicos",
    "018": "Coca Cola",
}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_product(raw: dict[str, Any], category: str) -> ArenaProduct:
    price = raw.get("price") or {}
    price = price.get("defaultPrice") or price
    sales = price.get("sales") or {}
    listed = price.get("list") or {}
    difference = price.get("priceDiff") or {}
    sales_price = _number(sales.get("value"))
    regular_price = _number(listed.get("value")) or sales_price

    tiers: list[TierPrice] = []
    for tier in price.get("tiers") or []:
        tier_price = ((tier.get("price") or {}).get("sales") or {}).get("value")
        if tier_price is not None:
            tiers.append(TierPrice(int(tier.get("quantity") or 1), float(tier_price)))

    images = (raw.get("images") or {}).get("large") or []
    image_url = images[0].get("absURL") if images else None
    tags = []
    for tag in raw.get("tags") or []:
        if isinstance(tag, str):
            tags.append(tag)
        elif isinstance(tag, dict):
            value = tag.get("name") or tag.get("label") or tag.get("id")
            if value:
                tags.append(str(value))
    if raw.get("promotionDiscount") and "promotion" not in tags:
        tags.append("promotion")

    return ArenaProduct(
        id=str(raw["id"]),
        name=str(raw.get("productName") or "").strip(),
        brand=(str(raw["brand"]).strip() if raw.get("brand") else None),
        categories=[category],
        available=bool(raw.get("available") and raw.get("isActiveInCurrentStore", True)),
        stock=_number(raw.get("ATSInCurrentStore")),
        regular_price=regular_price,
        sales_price=sales_price,
        discount=_number(difference.get("value")),
        tier_prices=tiers,
        image_url=image_url,
        product_url=raw.get("productShowFullUrl"),
        measure=raw.get("productMeasureValue"),
        internal_code=str(raw["id"]),
        offer_tags=tags,
    )


class SaoVicenteCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None, page_size: int = 1200):
        self.client = client
        self.page_size = page_size

    async def _select_store(self, client: httpx.AsyncClient) -> None:
        response = await client.get(SOURCE_URL)
        response.raise_for_status()
        response = await client.get(
            SELECT_STORE_URL,
            params={"storeID": STORE_ID, "method": "Retirada"},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError("São Vicente did not accept the Hortolândia store")

        response = await client.get(AVAILABLE_STORES_URL)
        response.raise_for_status()
        active = next(
            (store for store in response.json().get("stores") or [] if store.get("active")),
            None,
        )
        if active is None or str(active.get("storeId")) != STORE_ID:
            raise RuntimeError("São Vicente Hortolândia store was not activated")

    async def _department(
        self, client: httpx.AsyncClient, category_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        products: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        start = 0
        while True:
            try:
                response = await client.get(
                    SEARCH_URL,
                    params={"cgid": category_id, "start": start, "sz": self.page_size},
                )
                response.raise_for_status()
            except Exception as error:
                errors.append(collection_issue(f"department={category_id} start={start}", error))
                return products, errors
            payload = response.json()
            page = payload.get("productsSearchResult") or []
            products.extend(page)
            total = int((payload.get("productSearch") or {}).get("count") or 0)
            if not page or len(products) >= total:
                return products, errors
            start += len(page)

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=90,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "offer-monitoring/0.1"},
        )
        try:
            await self._select_store(client)
            merged: dict[str, ArenaProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for category_id, category in DEPARTMENTS.items():
                raw_products, errors = await self._department(client, category_id)
                collection_errors.extend(errors)
                department_counts[category] = len(raw_products)
                for raw in raw_products:
                    product = parse_product(raw, category)
                    existing = merged.get(product.id)
                    if existing is None:
                        merged[product.id] = product
                    elif category not in existing.categories:
                        existing.categories.append(category)
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            return {
                "retailer": "São Vicente",
                "source": SOURCE_URL,
                "collected_at": datetime.now(UTC).isoformat(),
                "store": STORE,
                "department_counts": department_counts,
                "product_count": len(products),
                "products": [asdict(product) for product in products],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()
