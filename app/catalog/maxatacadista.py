from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct
from app.catalog.resilience import collection_issue, collection_metadata, require_products

API_BASE_URL = "https://max-api.muffato.io/api/v1/customer"
DEPARTMENTS_URL = f"{API_BASE_URL}/webservice/departments"
PRODUCTS_URL = f"{API_BASE_URL}/webservice/products"
SOURCE_URL = "https://max-api.muffato.io/"

# There is no Max Atacadista branch in Hortolandia in the public store directory.
# Store 141 in Campinas is the closest regional reference returned by the API for
# the same Hortolandia reference ZIP code used by the other collectors.
REFERENCE_ZIP_CODE = "13184222"
STORE_CODE = "141"
STORE_API_ID = 606
STORE = {
    "id": STORE_API_ID,
    "code": STORE_CODE,
    "name": "Max Atacadista Campinas",
    "city": "Campinas",
    "state": "SP",
    "reference_zip_code": REFERENCE_ZIP_CODE,
    "selection_reason": "regional reference for Hortolândia; no local branch in public API",
}


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    return float(value)


def _ean(value: Any) -> str | None:
    code = str(value or "").strip()
    return code if code.isdigit() and len(code) in {8, 12, 13, 14} else None


def _secure_image_url(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    if url.startswith("http://s3.amazonaws.com/"):
        return "https://s3.amazonaws.com/" + url.removeprefix("http://s3.amazonaws.com/")
    return url


def parse_product(raw: dict[str, Any], department: str) -> ArenaProduct:
    external_id = str(raw.get("bismt") or raw.get("ean11") or "").strip()
    if not external_id:
        raise ValueError("Max product has neither bismt nor ean11")

    stock = _number(raw.get("estoque"))
    price = _number(raw.get("preco1"))
    brand = str(raw.get("desc_mercadologica") or "").strip() or None

    return ArenaProduct(
        id=external_id,
        name=str(raw.get("descricao") or "").strip(),
        brand=brand[:160] if brand else None,
        categories=[department],
        available=stock is not None and stock > 0,
        stock=stock,
        regular_price=price,
        sales_price=price,
        image_url=_secure_image_url(raw.get("imagem")),
        measure=str(raw.get("unidade_medida") or "").strip() or None,
        ean=_ean(raw.get("ean11")),
        internal_code=str(raw.get("bismt") or "").strip() or None,
    )


class MaxAtacadistaCatalogClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        store_code: str = STORE_CODE,
        page_size: int = 100,
        concurrency: int = 6,
        max_pages: int | None = None,
    ):
        self.client = client
        self.store_code = store_code
        self.page_size = page_size
        self.concurrency = concurrency
        self.max_pages = max_pages
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
        self, client: httpx.AsyncClient, department_id: int, page: int
    ) -> dict[str, Any]:
        return await self._get_json(
            client,
            PRODUCTS_URL,
            params={
                "cod_store": self.store_code,
                "department": department_id,
                "search": "",
                "limit": self.page_size,
                "page": page,
            },
        )

    async def _department(
        self, client: httpx.AsyncClient, department_id: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        products: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        page = 1
        while self.max_pages is None or page <= self.max_pages:
            try:
                payload = await self._page(client, department_id, page)
            except Exception as error:
                errors.append(collection_issue(f"department={department_id} page={page}", error))
                break
            page_products = list(payload.get("results") or [])
            products.extend(page_products)
            if not payload.get("next") or not page_products:
                break
            page += 1
        return products, errors

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=self.concurrency),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Language": "pt",
                "App-Version": "2.0.31",
                "User-Agent": "offer-monitoring/0.1",
            },
        )
        try:
            departments = await self._get_json(client, DEPARTMENTS_URL)
            department_results = await asyncio.gather(
                *(
                    self._department(client, int(department["id"]))
                    for department in departments
                ),
                return_exceptions=True,
            )

            merged: dict[str, ArenaProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department, result in zip(departments, department_results, strict=True):
                department_id = int(department["id"])
                department_name = str(department.get("descricao") or "Outros").strip()
                if isinstance(result, BaseException):
                    collection_errors.append(
                        collection_issue(f"department={department_id} page=1", result)
                    )
                    department_counts[department_name] = 0
                    continue

                raw_products, errors = result
                collection_errors.extend(errors)
                department_counts[department_name] = len(raw_products)
                for index, raw in enumerate(raw_products, start=1):
                    try:
                        product = parse_product(raw, department_name)
                    except Exception as error:
                        collection_errors.append(
                            collection_issue(
                                f"department={department_id} product={index}", error
                            )
                        )
                        continue
                    existing = merged.get(product.id)
                    if existing is None:
                        merged[product.id] = product
                        continue
                    if department_name not in existing.categories:
                        existing.categories.append(department_name)
                    if existing.sales_price is None and product.sales_price is not None:
                        existing.regular_price = product.regular_price
                        existing.sales_price = product.sales_price
                    if (existing.stock or 0) < (product.stock or 0):
                        existing.stock = product.stock
                        existing.available = product.available

            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            return {
                "retailer": "Max Atacadista",
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
