from __future__ import annotations

import asyncio
import re
import string
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.catalog.resilience import collection_issue, collection_metadata, require_products
from app.core.config import get_settings

API_URL = "https://api-clientes.assai.com.br"
STORE_ID = "175"
STORE_CODE = "173"
APP_VERSION = "10.10.4"
PAGE_SIZE = 200
SEARCH_TERMS = string.ascii_lowercase + string.digits
SEARCH_CONCURRENCY = 8


def _positive_price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    result = float(value)
    return result if result > 0 else None


def _ean(value: Any) -> str | None:
    result = str(value or "").strip()
    return result if 8 <= len(result) <= 14 and result.isdigit() else None


def parse_product(raw: dict[str, Any]) -> ArenaProduct:
    """Parse an authenticated promotion from the CRM discounts endpoint."""
    retail_price = _positive_price(raw.get("retail_price"))
    wholesale_price = _positive_price(raw.get("wholesale_price"))
    app_price = _positive_price(raw.get("app_price"))
    sales_price = app_price or wholesale_price or retail_price
    minimum_quantity = max(1, int(raw.get("quantity") or 1))
    tiers: list[TierPrice] = []
    if wholesale_price is not None and minimum_quantity > 1:
        tiers.append(TierPrice(minimum_quantity, wholesale_price))
    if app_price is not None:
        tiers.append(TierPrice(minimum_quantity, app_price, condition="app"))
    tags = ["promotion", "authenticated-catalog"]
    if raw.get("start_date"):
        tags.append(f"valid-from:{str(raw['start_date'])[:10]}")
    if raw.get("end_date"):
        tags.append(f"valid-until:{str(raw['end_date'])[:10]}")
    external_id = raw.get("product_id") or raw.get("ean") or raw.get("id")
    category = str(raw.get("category_name") or "").strip()
    return ArenaProduct(
        id=str(external_id),
        name=str(raw.get("description_product") or "").strip(),
        brand=None,
        categories=[category] if category else [],
        available=True,
        stock=None,
        regular_price=retail_price or sales_price,
        sales_price=sales_price,
        discount=(
            max(0.0, retail_price - sales_price)
            if retail_price is not None and sales_price is not None
            else None
        ),
        tier_prices=tiers,
        image_url=raw.get("main_image_url"),
        product_url=None,
        measure="KG" if raw.get("is_heavy_product") == 1 else "UN",
        ean=_ean(raw.get("ean")),
        internal_code=str(raw.get("id") or "").strip() or None,
        offer_tags=tags,
    )


def parse_catalog_product(raw: dict[str, Any]) -> ArenaProduct:
    """Parse a product returned by the full store search endpoint."""
    retail_price = _positive_price(raw.get("retail_value"))
    wholesale_price = _positive_price(raw.get("wholesale_value"))
    sales_price = wholesale_price or retail_price
    has_price = bool(raw.get("has_a_price")) and sales_price is not None
    tiers: list[TierPrice] = []
    if wholesale_price is not None and wholesale_price != retail_price:
        tiers.append(TierPrice(1, wholesale_price, condition="wholesale"))
    product_id = str(raw.get("product_id") or raw.get("ean") or "").strip()
    return ArenaProduct(
        id=product_id,
        name=str(raw.get("description_product") or "").strip(),
        brand=str(raw.get("brand") or "").strip() or None,
        available=has_price,
        stock=None,
        regular_price=retail_price or sales_price,
        sales_price=sales_price if has_price else None,
        discount=(
            max(0.0, retail_price - sales_price)
            if has_price and retail_price is not None and sales_price is not None
            else None
        ),
        tier_prices=tiers,
        image_url=raw.get("main_image_url"),
        product_url=None,
        measure=str(raw.get("base_unit") or "").upper() or None,
        ean=_ean(raw.get("ean")),
        internal_code=product_id or None,
        offer_tags=["full-catalog"],
    )


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "products"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


class AssaiCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    @staticmethod
    def _bundle_config() -> tuple[str, str, str]:
        path = get_settings().assai_bundle_file
        if not path.is_file():
            raise RuntimeError(f"Meu Assai bundle not found at {path}")
        source = path.read_text(encoding="utf-8")
        basic = re.search(r"basicToken': '([^']+)'", source)
        cognito = re.search(
            r"r3 = '(sa-east-1_[A-Za-z0-9]+)';(?s:.{0,400}?)r1 = '([a-z0-9]{26})';",
            source,
        )
        if basic is None or cognito is None:
            raise RuntimeError("Meu Assai API configuration was not found in the bundle")
        return basic.group(1), cognito.group(1), cognito.group(2)

    @staticmethod
    def _credentials() -> tuple[str, str]:
        settings = get_settings()
        if not settings.assai_username or not settings.assai_password:
            raise RuntimeError("ASSAI_USERNAME and ASSAI_PASSWORD must be configured")
        username = re.sub(r"\D", "", settings.assai_username)
        if len(username) not in (11, 14):
            raise RuntimeError("ASSAI_USERNAME must contain a valid CPF or CNPJ")
        return username, settings.assai_password.get_secret_value()

    async def _authenticate(
        self, client: httpx.AsyncClient, user_pool_id: str, client_id: str
    ) -> str:
        username, password = self._credentials()
        region = user_pool_id.split("_", 1)[0]
        response = await client.post(
            f"https://cognito-idp.{region}.amazonaws.com/",
            headers={
                "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
                "Content-Type": "application/x-amz-json-1.1",
            },
            json={
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": client_id,
                "AuthParameters": {"USERNAME": username, "PASSWORD": password},
            },
        )
        if response.status_code == 400:
            error_type = str(response.json().get("__type") or "").split("#")[-1]
            if error_type == "NotAuthorizedException":
                raise RuntimeError("Meu Assai credentials were rejected by Cognito")
        response.raise_for_status()
        payload = response.json()
        if payload.get("ChallengeName"):
            raise RuntimeError(f"Meu Assai login requires {payload['ChallengeName']}")
        token = (payload.get("AuthenticationResult") or {}).get("AccessToken")
        if not token:
            raise RuntimeError("Meu Assai Cognito did not return an access token")
        return str(token)

    @staticmethod
    def _headers(basic: str, token: str) -> dict[str, str]:
        return {
            "X-BasicAuthorization": basic,
            "Authorization": token,
            "X-device-uuid": str(uuid.uuid4()),
            "X-Installation-Info": f"{APP_VERSION};Samsung;SM-S918B;dm3q;android;14",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": f"MeuAssai/{APP_VERSION} (android; 14; Samsung SM-S918B)",
            "Accept": "application/json",
        }

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
        semaphore: asyncio.Semaphore | None = None,
    ) -> dict[str, Any]:
        for attempt in range(4):
            try:
                if semaphore is None:
                    response = await client.get(url, params=params, headers=headers)
                else:
                    async with semaphore:
                        response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 3:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("unreachable")

    async def _catalog_page(
        self, client: httpx.AsyncClient, headers: dict[str, str], page: int
    ) -> dict[str, Any]:
        return await self._request_json(
            client,
            f"{API_URL}/crm/store/{STORE_ID}/discounts",
            headers,
            {"store_id": STORE_ID, "page": page, "size": PAGE_SIZE},
        )

    async def _collect_search_term(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        term: str,
        products: dict[str, ArenaProduct],
        semaphore: asyncio.Semaphore,
        collection_errors: list[dict[str, str]],
    ) -> int:
        page = 1
        total_pages = 1
        item_count = 0
        while page <= total_pages:
            try:
                payload = await self._request_json(
                    client,
                    f"{API_URL}/shopping/store/{STORE_CODE}/product-search/{term}",
                    headers,
                    {"page": page, "size": PAGE_SIZE},
                    semaphore,
                )
            except Exception as error:
                collection_errors.append(collection_issue(f"search={term} page={page}", error))
                return item_count
            items = _extract_items(payload)
            item_count += len(items)
            for raw in items:
                product = parse_catalog_product(raw)
                if product.id and product.name:
                    products[product.id] = product
            total_pages = max(1, int(payload.get("total_pages") or 1))
            page += 1
        return item_count

    async def _promotions(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        collection_errors: list[dict[str, str]],
    ) -> list[ArenaProduct]:
        products: dict[str, ArenaProduct] = {}
        page = 1
        while True:
            try:
                payload = await self._catalog_page(client, headers, page)
            except Exception as error:
                collection_errors.append(collection_issue(f"promotions page={page}", error))
                return list(products.values())
            items = _extract_items(payload)
            for raw in items:
                product = parse_product(raw)
                products[product.id] = product
            if len(items) < PAGE_SIZE:
                return list(products.values())
            page += 1
            if page > 500:
                raise RuntimeError("Meu Assai promotions pagination exceeded 500 pages")

    @staticmethod
    def _merge_promotion(product: ArenaProduct, promotion: ArenaProduct) -> None:
        product.available = True
        product.regular_price = promotion.regular_price or product.regular_price
        product.sales_price = promotion.sales_price or product.sales_price
        product.discount = promotion.discount
        product.categories = promotion.categories or product.categories
        product.tier_prices = promotion.tier_prices or product.tier_prices
        product.image_url = promotion.image_url or product.image_url
        product.ean = promotion.ean or product.ean
        product.offer_tags = list(dict.fromkeys(product.offer_tags + promotion.offer_tags))

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=60, follow_redirects=True)
        try:
            basic, user_pool_id, client_id = self._bundle_config()
            token = await self._authenticate(client, user_pool_id, client_id)
            headers = self._headers(basic, token)
            products: dict[str, ArenaProduct] = {}
            collection_errors: list[dict[str, str]] = []
            semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)
            counts = await asyncio.gather(
                *(
                    self._collect_search_term(
                        client, headers, term, products, semaphore, collection_errors
                    )
                    for term in SEARCH_TERMS
                )
            )
            promotions = await self._promotions(client, headers, collection_errors)
            for promotion in promotions:
                product = products.get(promotion.id)
                if product is None:
                    products[promotion.id] = promotion
                else:
                    self._merge_promotion(product, promotion)
            ordered = sorted(products.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(ordered, collection_errors)
            return {
                "retailer": "Assaí Atacadista",
                "source": f"{API_URL}/shopping/store/{STORE_CODE}/product-search",
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": {
                    "full-catalog": len(ordered),
                    "search-results-before-deduplication": sum(counts),
                    "authenticated-promotions": len(promotions),
                },
                "store": {
                    "name": "Assaí Hortolândia – Loja 175",
                    "city": "Hortolândia",
                    "state": "SP",
                    "store_id": STORE_ID,
                    "store_code": STORE_CODE,
                },
                "promotion_count": len(promotions),
                "product_count": len(ordered),
                "products": [asdict(product) for product in ordered],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()
