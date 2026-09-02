from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.catalog.resilience import collection_issue, collection_metadata, require_products
from app.core.config import get_settings

API_URL = "https://api.tendaatacado.com.br/api"
DEPARTMENTS_URL = f"{API_URL}/public/store/departments"
CATEGORY_URL = f"{API_URL}/public/store/category/{{category_id}}/products"
SOURCE_URL = "https://www.tendaatacado.com.br/"

# Same reference CEP used by the other Hortolandia collectors. The public
# branch lookup resolves it to CT39 - Tenda Hortolandia.
REFERENCE_ZIP_CODE = "13184222"
BRANCH_ID = "46"
BRANCH_CODE = "CT39"
STORE = {
    "id": int(BRANCH_ID),
    "code": BRANCH_CODE,
    "name": "Tenda Hortolândia",
    "city": "Hortolândia",
    "state": "SP",
    "zip_code": REFERENCE_ZIP_CODE,
}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _ean(value: Any) -> str | None:
    code = str(value or "").strip()
    return code if code.isdigit() and len(code) in {8, 12, 13, 14} else None


def _local_stock(raw: dict[str, Any], branch_id: str) -> float:
    for inventory in raw.get("inventory") or []:
        if str(inventory.get("branchId")) == branch_id:
            return float(inventory.get("totalAvailable") or 0)
    return 0.0


def parse_product(
    raw: dict[str, Any], category: str, branch_id: str = BRANCH_ID
) -> ArenaProduct:
    regular_price = _number(raw.get("price"))
    promotion = raw.get("promotion") or {}
    sales_price = _number(promotion.get("price")) or regular_price
    stock = _local_stock(raw, branch_id)

    tiers: list[TierPrice] = []
    for tier in raw.get("wholesalePrices") or []:
        price = _number(tier.get("price"))
        if price is not None:
            tiers.append(TierPrice(int(tier.get("minQuantity") or 1), price))

    offer_tags: list[str] = []
    if promotion:
        offer_tags.append("promotion")
    for app_promotion in raw.get("promotions") or []:
        price = _number(app_promotion.get("price"))
        template = str(app_promotion.get("template") or "app").strip().casefold()
        if price is not None:
            tiers.append(TierPrice(1, price, condition="app"))
        tag = f"app:{template}"
        if tag not in offer_tags:
            offer_tags.append(tag)

    source_categories = [category]
    raw_department = raw.get("department") or {}
    department_name = raw_department.get("name") if isinstance(raw_department, dict) else None
    if department_name and department_name not in source_categories:
        source_categories.append(str(department_name))

    sku = str(raw.get("sku") or "").strip() or None
    if sku and len(sku) > 120:
        sku = None
    measure = None
    if sku and "-" in sku:
        measure = sku.rsplit("-", 1)[-1]

    return ArenaProduct(
        id=str(raw.get("id") or sku),
        name=str(raw.get("name") or "").strip(),
        brand=(str(raw["brand"]).strip()[:160] if raw.get("brand") else None),
        categories=source_categories,
        available=stock > 0,
        stock=stock,
        regular_price=regular_price,
        sales_price=sales_price,
        discount=(
            round(regular_price - sales_price, 2)
            if regular_price is not None
            and sales_price is not None
            and regular_price > sales_price
            else None
        ),
        tier_prices=tiers,
        image_url=raw.get("thumbnail"),
        product_url=raw.get("url"),
        measure=measure,
        ean=_ean(raw.get("barcode")),
        internal_code=sku,
        offer_tags=offer_tags,
    )


class TendaCatalogClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        branch_id: str = BRANCH_ID,
        concurrency: int = 12,
        max_pages: int | None = None,
        proxy_url: str | None = None,
    ):
        self.client = client
        self.branch_id = branch_id
        self.concurrency = concurrency
        self.max_pages = max_pages
        self.proxy_url = proxy_url
        self._semaphore = asyncio.Semaphore(concurrency)

    async def _get_json(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> Any:
        async with self._semaphore:
            for attempt in range(3):
                response = await client.get(url, params=params)
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    return response.json()
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
            response.raise_for_status()

    async def _page(
        self, client: httpx.AsyncClient, category_id: int, page: int
    ) -> dict[str, Any]:
        return await self._get_json(
            client,
            CATEGORY_URL.format(category_id=category_id),
            params={"page": page, "order": "relevance", "save": "false"},
        )

    async def _department(
        self, client: httpx.AsyncClient, category_id: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        first = await self._page(client, category_id, 1)
        errors: list[dict[str, str]] = []
        total_pages = int(first.get("total_pages") or 1)
        if self.max_pages is not None:
            total_pages = min(total_pages, self.max_pages)
        if total_pages == 1:
            return list(first.get("products") or []), errors
        page_numbers = list(range(2, total_pages + 1))
        pages = await asyncio.gather(
            *(self._page(client, category_id, page) for page in page_numbers),
            return_exceptions=True,
        )
        products = list(first.get("products") or [])
        for page_number, payload in zip(page_numbers, pages, strict=True):
            if isinstance(payload, BaseException):
                errors.append(
                    collection_issue(f"department={category_id} page={page_number}", payload)
                )
                continue
            products.extend(payload.get("products") or [])
        return products, errors

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client
        if owns_client:
            proxy_url = (
                self.proxy_url
                if self.proxy_url is not None
                else get_settings().tenda_proxy_url
            )
            client_kwargs: dict[str, Any] = {
                "timeout": 60,
                "follow_redirects": True,
                "limits": httpx.Limits(max_connections=self.concurrency),
                "headers": {
                    "Accept": "application/json",
                    "Content-Type": "application/json; charset=utf-8",
                    "desktop-platform": "true",
                    "User-Agent": "offer-monitoring/0.1",
                },
            }
            if proxy_url:
                client_kwargs["proxy"] = proxy_url
            client = httpx.AsyncClient(**client_kwargs)
        try:
            departments = await self._get_json(client, DEPARTMENTS_URL)
            department_products = await asyncio.gather(
                *(self._department(client, int(department["id"])) for department in departments),
                return_exceptions=True,
            )
            merged: dict[str, ArenaProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department, result in zip(departments, department_products, strict=True):
                category = str(department.get("name") or "Outros").strip()
                if isinstance(result, BaseException):
                    collection_errors.append(
                        collection_issue(f"department={department.get('id')} page=1", result)
                    )
                    department_counts[category] = 0
                    continue
                raw_products, errors = result
                collection_errors.extend(errors)
                department_counts[category] = len(raw_products)
                for raw in raw_products:
                    product = parse_product(raw, category, self.branch_id)
                    existing = merged.get(product.id)
                    if existing is None:
                        merged[product.id] = product
                    else:
                        for source_category in product.categories:
                            if source_category not in existing.categories:
                                existing.categories.append(source_category)

            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            return {
                "retailer": "Tenda Atacado",
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
