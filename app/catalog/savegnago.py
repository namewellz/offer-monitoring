from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct
from app.catalog.atacadao import _leaf_categories, _top_categories

ACCOUNT_URL = "https://savegnagoio.vtexcommercestable.com.br"
SEARCH_URL = f"{ACCOUNT_URL}/api/catalog_system/pub/products/search"
CATEGORY_TREE_URL = f"{ACCOUNT_URL}/api/catalog_system/pub/category/tree/5"
SITE_URL = "https://www.savegnago.com.br"
SIMULATION_URL = f"{SITE_URL}/api/checkout/pub/orderForms/simulation"
WEEKLY_OFFERS_CLUSTER = "4601"
PAGE_SIZE = 50
POSTAL_CODE = "13184222"
SALES_CHANNEL = "1"
SELLER_ID = "1"
SIMULATION_BATCH_SIZE = 100


def _price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    return number if number > 0 else None


def parse_products(raw: dict[str, Any], weekly_offer: bool = False) -> list[ArenaProduct]:
    categories = [str(value).strip("/") for value in raw.get("categories") or []]
    products = []
    for item in raw.get("items") or []:
        sellers = item.get("sellers") or []
        seller = next((value for value in sellers if value.get("sellerDefault")), None)
        seller = seller or (sellers[0] if sellers else {})
        offer = seller.get("commertialOffer") or {}
        sales_price = _price(offer.get("Price"))
        regular_price = _price(offer.get("ListPrice")) or sales_price
        discount = None
        if regular_price is not None and sales_price is not None:
            discount = max(0.0, regular_price - sales_price)
        images = item.get("images") or []
        slug = raw.get("linkText")
        products.append(
            ArenaProduct(
                id=str(item["itemId"]),
                name=str(
                    item.get("nameComplete") or item.get("name") or raw.get("productName") or ""
                ).strip(),
                brand=(str(raw["brand"]).strip() if raw.get("brand") else None),
                categories=categories,
                available=bool(offer.get("IsAvailable")),
                stock=float(offer["AvailableQuantity"])
                if offer.get("AvailableQuantity") is not None
                else None,
                regular_price=regular_price,
                sales_price=sales_price,
                discount=discount,
                image_url=images[0].get("imageUrl") if images else None,
                product_url=f"{SITE_URL}/{slug}/p" if slug else None,
                measure=item.get("measurementUnit"),
                ean=str(item["ean"]).strip()
                if item.get("ean") and str(item["ean"]).strip() != "0"
                else None,
                internal_code=str(
                    raw.get("productReferenceCode") or raw.get("productReference") or ""
                ).strip()
                or None,
                offer_tags=["weekly-offers"] if weekly_offer else [],
            )
        )
    return products


class SavegnagoCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None, concurrency: int = 12):
        self.client = client
        self.concurrency = concurrency

    async def _request(self, client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
        for attempt in range(4):
            try:
                response = await client.get(SEARCH_URL, params=params)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 3:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("unreachable")

    async def _query(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        filters: str | list[str],
    ) -> tuple[int, list[dict[str, Any]]]:
        async with semaphore:
            first = await self._request(client, {"fq": filters, "_from": 0, "_to": PAGE_SIZE - 1})
        match = re.search(r"/(\d+)$", first.headers.get("resources", ""))
        total = int(match.group(1)) if match else len(first.json())
        fetch_total = min(total, 2501)

        async def page(start: int) -> list[dict[str, Any]]:
            async with semaphore:
                response = await self._request(
                    client,
                    {
                        "fq": filters,
                        "_from": start,
                        "_to": min(start + PAGE_SIZE - 1, fetch_total - 1),
                    },
                )
            return response.json()

        pages = [first.json()]
        if fetch_total > PAGE_SIZE:
            pages.extend(
                await asyncio.gather(
                    *(page(start) for start in range(PAGE_SIZE, fetch_total, PAGE_SIZE))
                )
            )
        return total, [product for values in pages for product in values]

    async def _simulation(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        products: list[ArenaProduct],
    ) -> list[dict[str, Any]]:
        body = {
            "items": [
                {"id": product.id, "quantity": 1, "seller": SELLER_ID} for product in products
            ],
            "postalCode": POSTAL_CODE,
            "country": "BRA",
        }
        for attempt in range(4):
            try:
                async with semaphore:
                    response = await client.post(
                        SIMULATION_URL,
                        params={"sc": SALES_CHANNEL, "RnbBehavior": "0"},
                        json=body,
                    )
                response.raise_for_status()
                return response.json().get("items") or []
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 3:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("unreachable")

    async def _apply_store_prices(
        self, client: httpx.AsyncClient, products: list[ArenaProduct]
    ) -> None:
        for product in products:
            product.available = False
            product.stock = None
            product.regular_price = None
            product.sales_price = None
            product.discount = None
        batches = [
            products[start : start + SIMULATION_BATCH_SIZE]
            for start in range(0, len(products), SIMULATION_BATCH_SIZE)
        ]
        semaphore = asyncio.Semaphore(self.concurrency)
        responses = await asyncio.gather(
            *(self._simulation(client, semaphore, batch) for batch in batches)
        )
        by_id = {product.id: product for product in products}
        for raw in (item for response in responses for item in response):
            product = by_id.get(str(raw.get("id")))
            if product is None:
                continue
            product.available = raw.get("availability") == "available"
            product.sales_price = _price(raw.get("price"))
            product.regular_price = _price(raw.get("listPrice")) or product.sales_price
            if product.sales_price is not None:
                product.sales_price /= 100
            if product.regular_price is not None:
                product.regular_price /= 100
            if product.regular_price is not None and product.sales_price is not None:
                product.discount = max(0.0, product.regular_price - product.sales_price)

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.concurrency,
                max_keepalive_connections=self.concurrency,
            ),
            headers={"Accept": "application/json", "User-Agent": "offer-monitoring/0.1"},
        )
        try:
            tree_response = await client.get(CATEGORY_TREE_URL)
            tree_response.raise_for_status()
            tree = tree_response.json()
            queries: list[tuple[str, str | list[str], bool]] = [
                (f"{fq} {name}", fq, False) for fq, name in _leaf_categories(tree)
            ]
            queries.extend(
                (
                    f"available {name}",
                    [fq, "isAvailablePerSalesChannel_1:1"],
                    False,
                )
                for fq, name in _top_categories(tree)
            )
            queries.append(
                (
                    "weekly-offers",
                    f"H:{WEEKLY_OFFERS_CLUSTER}",
                    True,
                )
            )
            semaphore = asyncio.Semaphore(self.concurrency)
            results = await asyncio.gather(
                *(self._query(client, semaphore, filters) for _, filters, _ in queries)
            )
            merged: dict[str, ArenaProduct] = {}
            query_counts = {}
            for (label, _, weekly_offer), (total, raw_products) in zip(
                queries, results, strict=True
            ):
                query_counts[label] = total
                for raw in raw_products:
                    for product in parse_products(raw, weekly_offer=weekly_offer):
                        existing = merged.get(product.id)
                        if existing:
                            for category in product.categories:
                                if category not in existing.categories:
                                    existing.categories.append(category)
                            for tag in product.offer_tags:
                                if tag not in existing.offer_tags:
                                    existing.offer_tags.append(tag)
                        else:
                            merged[product.id] = product
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            await self._apply_store_prices(client, products)
            return {
                "retailer": "Savegnago",
                "source": SEARCH_URL,
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": query_counts,
                "store": {
                    "name": "Hortolândia - Hortolândia - LJ 55",
                    "city": "Hortolândia",
                    "state": "SP",
                    "postal_code": "13184-222",
                    "address": "Rua Luiz Camilo de Camargo, 322",
                    "pickup_point_id": "savegnagoiohortolandia55_3da49e81-0e83-457a-a5a1-3d198ab464af",
                    "pickup_name": "Retira Loja 55",
                    "sales_channel": SALES_CHANNEL,
                    "seller": SELLER_ID,
                },
                "weekly_offer_count": sum(
                    "weekly-offers" in product.offer_tags for product in products
                ),
                "product_count": len(products),
                "products": [asdict(product) for product in products],
            }
        finally:
            if owns_client:
                await client.aclose()
