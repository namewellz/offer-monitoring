from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct
from app.catalog.resilience import collection_issue, collection_metadata, require_products

ACCOUNT_URL = "https://atacadaobr.vtexcommercestable.com.br"
SEARCH_URL = f"{ACCOUNT_URL}/api/catalog_system/pub/products/search"
CATEGORY_TREE_URL = f"{ACCOUNT_URL}/api/catalog_system/pub/category/tree/5"
SITE_URL = "https://www.atacadao.com.br"
SIMULATION_URL = f"{SITE_URL}/api/checkout/pub/orderForms/simulation"
PAGE_SIZE = 50
POSTAL_CODE = "02170901"
SALES_CHANNEL = "1"
SELLER_ID = "atacadaobr60"
SIMULATION_BATCH_SIZE = 100


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _price(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def parse_products(raw: dict[str, Any]) -> list[ArenaProduct]:
    categories = [str(value).strip("/") for value in raw.get("categories") or []]
    products: list[ArenaProduct] = []
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
                name=str(item.get("nameComplete") or item.get("name") or raw.get("productName") or "").strip(),
                brand=(str(raw["brand"]).strip() if raw.get("brand") else None),
                categories=categories,
                available=bool(offer.get("IsAvailable")),
                stock=_number(offer.get("AvailableQuantity")),
                regular_price=regular_price,
                sales_price=sales_price,
                discount=discount,
                image_url=images[0].get("imageUrl") if images else None,
                product_url=f"{SITE_URL}/{slug}/p" if slug else None,
                measure=item.get("measurementUnit"),
                ean=str(item["ean"]).strip() if item.get("ean") else None,
                internal_code=str(raw.get("productReferenceCode") or raw.get("productReference") or "").strip() or None,
            )
        )
    return products


def _leaf_categories(nodes: list[dict[str, Any]], parent_ids: tuple[int, ...] = ()) -> list[tuple[str, str]]:
    leaves: list[tuple[str, str]] = []
    for node in nodes:
        path_ids = (*parent_ids, int(node["id"]))
        children = node.get("children") or []
        if children:
            leaves.extend(_leaf_categories(children, path_ids))
        else:
            leaves.append((f"C:/{'/'.join(map(str, path_ids))}/", str(node.get("name") or node["id"])))
    return leaves


def _top_categories(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(f"C:/{int(node['id'])}/", str(node.get("name") or node["id"])) for node in nodes]


class AtacadaoCatalogClient:
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

    async def _category(
        self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, fq: str | list[str]
    ) -> tuple[int, list[dict[str, Any]], list[dict[str, str]]]:
        async with semaphore:
            first = await self._request(client, {"fq": fq, "_from": 0, "_to": PAGE_SIZE - 1})
        match = re.search(r"/(\d+)$", first.headers.get("resources", ""))
        total = int(match.group(1)) if match else len(first.json())
        pages = [first.json()]
        errors: list[dict[str, str]] = []
        fetch_total = min(total, 2501)  # VTEX rejects _from values above 2500.

        async def fetch(start: int) -> list[dict[str, Any]]:
            async with semaphore:
                response = await self._request(
                    client,
                    {"fq": fq, "_from": start, "_to": min(start + PAGE_SIZE - 1, fetch_total - 1)},
                )
            return response.json()

        if fetch_total > PAGE_SIZE:
            starts = list(range(PAGE_SIZE, fetch_total, PAGE_SIZE))
            results = await asyncio.gather(
                *(fetch(start) for start in starts), return_exceptions=True
            )
            for start, result in zip(starts, results, strict=True):
                if isinstance(result, BaseException):
                    errors.append(collection_issue(f"filter={fq} start={start}", result))
                else:
                    pages.append(result)
        return total, [product for page in pages for product in page], errors

    async def _simulation(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        products: list[ArenaProduct],
    ) -> list[dict[str, Any]]:
        body = {
            "items": [
                {"id": product.id, "quantity": 1, "seller": SELLER_ID}
                for product in products
            ],
            "country": "BRA",
            "postalCode": POSTAL_CODE,
        }
        for attempt in range(4):
            try:
                async with semaphore:
                    response = await client.post(
                        SIMULATION_URL,
                        params={"sc": SALES_CHANNEL},
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
    ) -> list[dict[str, str]]:
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
        simulated_pages = await asyncio.gather(
            *(self._simulation(client, semaphore, batch) for batch in batches),
            return_exceptions=True,
        )
        errors: list[dict[str, str]] = []
        by_id = {product.id: product for product in products}
        valid_pages = []
        for index, page in enumerate(simulated_pages, start=1):
            if isinstance(page, BaseException):
                errors.append(collection_issue(f"price-simulation batch={index}", page))
            else:
                valid_pages.append(page)
        for raw in (item for page in valid_pages for item in page):
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
        return errors

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=self.concurrency, max_keepalive_connections=self.concurrency),
            headers={"Accept": "application/json", "User-Agent": "offer-monitoring/0.1"},
        )
        try:
            tree_response = await client.get(CATEGORY_TREE_URL)
            tree_response.raise_for_status()
            category_tree = tree_response.json()
            leaves = _leaf_categories(category_tree)
            # Leaf categories cover the historical catalog. Top-level categories plus
            # the availability filter also recover sellable products assigned directly
            # to a parent category rather than to a leaf.
            queries: list[tuple[str, str | list[str]]] = [
                (f"{fq} {name}", fq) for fq, name in leaves
            ]
            queries.extend(
                (f"available {name}", [fq, "isAvailablePerSalesChannel_1:1"])
                for fq, name in _top_categories(category_tree)
            )
            queries.append(("available root", "isAvailablePerSalesChannel_1:1"))
            semaphore = asyncio.Semaphore(self.concurrency)
            results = await asyncio.gather(
                *(self._category(client, semaphore, fq) for _, fq in queries),
                return_exceptions=True,
            )
            merged: dict[str, ArenaProduct] = {}
            category_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for (label, _), result in zip(queries, results, strict=True):
                if isinstance(result, BaseException):
                    collection_errors.append(collection_issue(label, result))
                    category_counts[label] = 0
                    continue
                total, raw_products, errors = result
                collection_errors.extend(errors)
                category_counts[label] = total
                for raw in raw_products:
                    for product in parse_products(raw):
                        existing = merged.get(product.id)
                        if existing:
                            for category in product.categories:
                                if category not in existing.categories:
                                    existing.categories.append(category)
                        else:
                            merged[product.id] = product
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            collection_errors.extend(await self._apply_store_prices(client, products))
            return {
                "retailer": "Atacadão",
                "source": SEARCH_URL,
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": category_counts,
                "store": {
                    "name": "Atacadão Vila Maria",
                    "city": "São Paulo",
                    "state": "SP",
                    "postal_code": "02170-901",
                    "address": "Avenida Morvan Dias de Figueiredo, 6157",
                    "sales_channel": SALES_CHANNEL,
                    "seller": SELLER_ID,
                },
                "product_count": len(products),
                "products": [asdict(product) for product in products],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()
