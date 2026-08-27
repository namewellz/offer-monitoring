from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.core.config import get_settings

API_URL = "https://api.mobilesim.com.br"
INIT_URL = f"{API_URL}/group/v1.02/init"
TABS_URL = f"{API_URL}/user/v1.02/tabs"
OFFERS_URL = f"{API_URL}/user/v1.03/offers"
STORE_CNPJ = "01707818000454"
EXPECTED_STORE_ID = "101"
APP_VERSION = "4.8.2"
APP_BUNDLE = "1"
PAGE_SIZE = 30


def _positive_price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    price = float(value)
    return price if price > 0 else None


def _ean(value: Any) -> str | None:
    barcode = str(value or "").strip()
    return barcode if 8 <= len(barcode) <= 14 and barcode.isdigit() else None


def parse_product(raw: dict[str, Any]) -> ArenaProduct:
    offer = raw.get("offer") or {}
    regular_price = _positive_price(raw.get("price"))
    offer_price = _positive_price(offer.get("offer_price")) or regular_price
    connect_price = _positive_price(offer.get("offer_connect"))
    tiers = []
    tags = ["promotion"]
    if connect_price is not None:
        tiers.append(TierPrice(1, connect_price, condition="club"))
        tags.append("connect-price")
    finish_date = str(offer.get("offer_finish_date") or "").strip()
    if finish_date:
        tags.append(f"valid-until:{finish_date}")
    categories = [f"category:{raw['catid']}"] if raw.get("catid") is not None else []
    if raw.get("subcatid") is not None:
        categories.append(f"subcategory:{raw['subcatid']}")
    return ArenaProduct(
        id=str(raw["sku"]),
        name=str(raw.get("name") or "").strip(),
        brand=None,
        categories=categories,
        available=True,
        stock=None,
        regular_price=regular_price,
        sales_price=offer_price,
        discount=(
            max(0.0, regular_price - offer_price)
            if regular_price is not None and offer_price is not None
            else None
        ),
        tier_prices=tiers,
        image_url=None,
        product_url=offer.get("share_link"),
        measure="KG" if raw.get("is_kg") == 1 else "UN",
        ean=_ean(raw.get("barcode")),
        internal_code=str(offer.get("offer_id") or "").strip() or None,
        offer_tags=tags,
    )


def _token_from_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("MAIN_API_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class DavitaCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None, concurrency: int = 6):
        self.client = client
        self.concurrency = concurrency

    def _token(self) -> str:
        settings = get_settings()
        token = settings.davita_api_token or _token_from_file(settings.davita_token_file)
        if not token:
            raise RuntimeError(
                "Davita API token is unavailable; configure DAVITA_API_TOKEN or "
                "DAVITA_TOKEN_FILE"
            )
        return token

    @staticmethod
    def _headers(token: str, store_id: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "isu": "0",
            "version": APP_VERSION,
            "bundle": APP_BUNDLE,
            "os": "0",
            "platform": "0",
            "Accept": "application/json",
        }
        if store_id:
            headers["store"] = store_id
        return headers

    async def _get(
        self, client: httpx.AsyncClient, url: str, headers: dict[str, str]
    ) -> dict[str, Any]:
        for attempt in range(4):
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if payload.get("cod") != 100:
                    raise RuntimeError(f"Davita API error: {payload.get('msg')}")
                return payload
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 3:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("unreachable")

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=45,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.concurrency,
                max_keepalive_connections=self.concurrency,
            ),
            headers={"User-Agent": "offer-monitoring/0.1"},
        )
        try:
            token = self._token()
            init_headers = self._headers(token)
            init_headers["cnpj"] = STORE_CNPJ
            init = (await self._get(client, INIT_URL, init_headers))["return"]
            store_id = str(init["store_id"])
            if store_id != EXPECTED_STORE_ID:
                raise RuntimeError(
                    f"Unexpected Davita store {store_id}; expected {EXPECTED_STORE_ID}"
                )
            store_headers = self._headers(token, store_id)
            tabs = (await self._get(client, TABS_URL, store_headers))["return"]
            offer_tab = next(
                (tab for tab in tabs if str(tab.get("name") or "").strip().upper() == "OFERTAS"),
                None,
            )
            if offer_tab is None:
                raise RuntimeError("Davita OFERTAS tab was not returned")
            tab_id = str(offer_tab["id"])
            first = await self._get(
                client, f"{OFFERS_URL}/0/0/{tab_id}", store_headers
            )
            first_return = first.get("return") or {}
            total = int(first_return.get("count") or 0)
            page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            semaphore = asyncio.Semaphore(self.concurrency)

            async def page(number: int) -> list[dict[str, Any]]:
                async with semaphore:
                    payload = await self._get(
                        client, f"{OFFERS_URL}/{number}/0/{tab_id}", store_headers
                    )
                return (payload.get("return") or {}).get("products") or []

            pages = [first_return.get("products") or []]
            if page_count > 1:
                pages.extend(await asyncio.gather(*(page(number) for number in range(1, page_count))))
            merged = {
                product.id: product
                for raw in (item for values in pages for item in values)
                for product in [parse_product(raw)]
            }
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            return {
                "retailer": "Davitta Supermercados",
                "source": f"{OFFERS_URL}/{{page}}/0/{tab_id}",
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": {"OFERTAS": total},
                "store": {
                    "name": "Loja 04 – Monte Mor",
                    "city": "Monte Mor",
                    "state": "SP",
                    "store_id": store_id,
                    "cnpj": STORE_CNPJ,
                    "tab_id": tab_id,
                },
                "promotion_count": len(products),
                "product_count": len(products),
                "products": [asdict(product) for product in products],
            }
        finally:
            if owns_client:
                await client.aclose()
