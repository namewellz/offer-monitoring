"""Catalog collector for Supermercados Pague Menos (Convertiez/Etrio SSR).

The storefront is server-rendered HTML. Every product card is an
``<div class="item-product" data-sku="...">`` containing:

* a lazy image (``data-src`` on the CDN ``io.convertiez.com.br``),
* the product name and the (optional) brand,
* ``.unit-price`` (the list price "de") and ``.sale-price`` (the selling price),
* a ``<form class="product-form" data-json='{item_id, item_name, item_brand,
  item_category1..3, price, discount}'>`` with a hidden ``price`` input that is
  the effective selling price.

Only products in stock render the form; out-of-stock items show an
"Avise-me" button and are skipped (they have no price).

Prices are the single online price list (CNPJ 60.494.416/0015-30) — the
footer states online prices may differ from physical stores, so collecting the
online department pages yields the price list used by the web channel.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.catalog.resilience import (
    collection_issue,
    collection_metadata,
    require_products,
)

BASE_URL = "https://www.superpaguemenos.com.br"
SITEMAP_CATEGORIES = (
    f"{BASE_URL}/s/superpaguemenos/sitemap-categories-1.xml"
)

# Real departments whose root page aggregates every product of the subtree.
# Marketing/collection sections (kits, festivos, jornal-de-ofertas, ...) are
# excluded because they only duplicate products already under a department.
#
# ``hortifruti`` and ``acougue`` are deliberately NOT collected yet: they sell by
# variable weight (per-gram price inputs + ".pricing-weight" average-unit block)
# and the listing price is not a reliable R$/kg. Capturing those correctly needs
# the product-detail page (which shows the R$/kg) and is left as a follow-up.
DEPARTMENTS = [
    "congelados",
    "higiene-e-beleza",
    "limpeza",
    "mercearia",
    "mamae-e-bebe",
    "bebidas",
    "cafe-da-manha",
    "frios-e-laticinios",
    "petshop",
    "bazar",
    "sopas-e-cremes",
    "especiais-e-saudaveis",
    "8518-eletro",
]

# CNPJ of the online operation (price authority; same as the site footer).
STORE_ID = "60.494.416/0015-30"
STORE_CODE = "loja-16-rosolen"
# Unit nearest Hortolândia (physically inside Hortolândia).
STORE_NAME = "Pague Menos Hortolândia (Loja 16 - Rosolen)"


@dataclass
class PaguemProduct:
    id: str
    name: str
    brand: str | None = None
    categories: list[str] = field(default_factory=list)
    available: bool = True
    stock: float | None = None
    regular_price: float | None = None
    sales_price: float | None = None
    discount: float | None = None
    tier_prices: list[dict[str, Any]] = field(default_factory=list)
    image_url: str | None = None
    product_url: str | None = None
    measure: str | None = None
    ean: str | None = None
    internal_code: str | None = None
    offer_tags: list[str] = field(default_factory=list)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_brl(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"([\d.]+,\d{2})", text)
    if not match:
        return None
    raw = match.group(1)
    return float(raw.replace(".", "").replace(",", "."))


def _categories_from_data_json(data: dict[str, Any]) -> list[str]:
    categories = []
    for key in ("item_category1", "item_category2", "item_category3"):
        value = (data.get(key) or "").strip()
        if value:
            categories.append(value)
    return categories


def parse_product(card: Any, soup: Any) -> PaguemProduct | None:
    """Parse one ``.item-product`` card into a PaguemProduct.

    Returns ``None`` for cards that are not reliably priced: out-of-stock items
    (no ``.product-form``), variable-weight items (a ``.pricing-weight`` block,
    e.g. produce/butcher sold per kg) and per-gram price artifacts.
    """
    if card.select_one(".pricing-weight") is not None:
        return None
    form = card.select_one("form.product-form[data-json]")
    if form is None:
        return None

    data_json: dict[str, Any] = {}
    try:
        import json

        data_json = json.loads(form.get("data-json") or "{}")
    except (ValueError, TypeError):
        data_json = {}

    price_input = form.select_one('input[name="price"]')
    sales_price = _number(price_input.get("value")) if price_input is not None else None
    regular_price = _number(data_json.get("price")) or sales_price
    if regular_price is not None and sales_price is not None and regular_price < sales_price:
        regular_price = sales_price

    product_input = form.select_one('input[name="product"]')
    raw_id = (
        card.get("data-sku")
        or (product_input.get("value") if product_input is not None else None)
        or str(data_json.get("item_id") or "")
    )
    product_id = str(raw_id)

    link = form.get("action") or ""
    title_node = card.select_one("h2.title a") or card.select_one("h2.title")
    name = (title_node.get_text(" ", strip=True) if title_node is not None else None) or (
        data_json.get("item_name") or ""
    )
    name = str(name).strip()

    image_node = card.select_one("img")
    image = None
    if image_node is not None:
        image = (
            image_node.get("data-src")
            or image_node.get("data-original")
            or image_node.get("src")
        )
    if image and image.startswith("//"):
        image = "https:" + image

    brand = (data_json.get("item_brand") or "").strip() or None
    if not brand:
        brand_node = card.select_one(".desc .font-size-11, .desc span.font-weight-bold")
        if brand_node is not None:
            brand = brand_node.get_text(" ", strip=True) or None

    # Per-gram artifact from a variable-weight product that slipped through:
    # never store a sub-R$0.50 price as the item price.
    if sales_price is not None and sales_price < 0.5:
        return None

    return PaguemProduct(
        id=str(product_id),
        name=name,
        brand=brand,
        categories=_categories_from_data_json(data_json),
        available=True,
        regular_price=regular_price,
        sales_price=sales_price,
        discount=_number(data_json.get("discount")),
        image_url=image,
        product_url=(BASE_URL + link) if link else None,
        internal_code=str(product_id) if product_id is not None else None,
    )


class PagueMenosCatalogClient:
    """Collects the Pague Menos online catalog from the department listing."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        departments: list[str] | None = None,
        max_pages: int = 250,
    ):
        self.client = client
        self.departments = departments or DEPARTMENTS
        self.max_pages = max_pages

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 offer-monitoring/0.1",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

    async def _fetch(
        self, client: httpx.AsyncClient, url: str
    ) -> BeautifulSoup:
        response = await client.get(url, headers=self._headers(), follow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    async def _department_page(
        self,
        client: httpx.AsyncClient,
        department_slug: str,
        page: int,
    ) -> list[PaguemProduct]:
        url = f"{BASE_URL}/{department_slug}/"
        if page > 1:
            url += f"?p={page}"
        soup = await self._fetch(client, url)
        products: list[PaguemProduct] = []
        for card in soup.select("div.item-product"):
            product = parse_product(card, soup)
            if product is not None:
                products.append(product)
        return products

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            headers=self._headers(),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
        )
        try:
            merged: dict[str, PaguemProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department_slug in self.departments:
                page = 1
                received = 0
                while page <= self.max_pages:
                    try:
                        items = await self._department_page(
                            client, department_slug, page
                        )
                    except Exception as error:
                        collection_errors.append(
                            collection_issue(
                                f"department={department_slug} page={page}", error
                            )
                        )
                        department_counts[department_slug] = received
                        break
                    if not items:
                        department_counts[department_slug] = received
                        break
                    for product in items:
                        existing = merged.get(product.id)
                        if existing is None:
                            merged[product.id] = product
                        else:
                            for category in product.categories:
                                if category not in existing.categories:
                                    existing.categories.append(category)
                    received += len(items)
                    if len(items) < 40:
                        department_counts[department_slug] = received
                        break
                    page += 1
                else:
                    department_counts[department_slug] = received

            products = sorted(
                merged.values(), key=lambda item: (item.name.casefold(), item.id)
            )
            require_products(products, collection_errors)
            return {
                "retailer": "Pague Menos",
                "source": f"{BASE_URL}/{{department}}/",
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": department_counts,
                "store": {
                    "name": STORE_NAME,
                    "city": "Hortolândia",
                    "state": "SP",
                    "postal_code": "13184-222",
                    "store_id": STORE_ID,
                    "store_code": STORE_CODE,
                    "sales_channel": "web",
                },
                "product_count": len(products),
                "products": [asdict(product) for product in products],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()
