"""Catalog collector for Supermercados Pague Menos (VTEX / FastStore).

Why this was rewritten
----------------------
Until Oct/2026 the storefront was server-rendered HTML (Convertiez/Etrio) and
the collector scraped ``div.item-product`` cards. The site was migrated to
**VTEX FastStore** (Next.js): the department pages now ship only
``#__NEXT_DATA__`` plus placeholder divs, so ``item-product`` matches nothing and
the whole collection failed with *"produced no usable products"*.

The same VTEX account, however, still exposes the classic catalog API used by
every VTEX store — and that is what we read now:

    GET /api/catalog_system/pub/category/tree/3          -> departamentos
    GET /api/catalog_system/pub/products/search?fq=C:/<id>/&_from&_to

Two quirks of that API:

* ranged searches answer **206 Partial Content** (not 200);
* the total comes in the ``resources`` header (``0-49/315``), and VTEX refuses
  ``_from`` above 2500 — a department is truncated there and we record it as a
  collection issue instead of silently losing the tail.

Departments bought by weight (``acougue``, ``hortifruti``) stay out: the listing
price is per kg/gram and is not comparable to packaged SKUs (same rule as the
previous scraper). ``festivos`` is a marketing cluster that only duplicates
products already listed under the real departments.

Prices are the online price list (CNPJ 60.494.416/0015-30); the site footer
states online prices may differ from the physical stores.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.resilience import collection_issue, collection_metadata, require_products

BASE_URL = "https://www.superpaguemenos.com.br"
CATEGORY_TREE_URL = f"{BASE_URL}/api/catalog_system/pub/category/tree/3"
SEARCH_URL = f"{BASE_URL}/api/catalog_system/pub/products/search"

# VTEX caps `_from` at 2500 on the public catalog API.
MAX_FROM = 2500
PAGE_SIZE = 50
# The public catalog API answers 500 when hammered; 4 in flight with retries is
# the sweet spot measured on 2026-11-01 (concurrency 6 produced 500s).
CONCURRENCY = 4
MAX_ATTEMPTS = 5

# Departments to skip (see module docstring). ``category`` is the placeholder
# root VTEX ships as id 1.
EXCLUDED_DEPARTMENTS = {"acougue", "hortifruti", "festivos", "category"}

# CNPJ of the online operation (price authority; same as the site footer).
STORE_ID = "60.494.416/0015-30"
STORE_CODE = "loja-16-rosolen"
# Unit nearest Hortolândia (physically inside Hortolândia).
STORE_NAME = "Pague Menos Hortolândia (Loja 16 - Rosolen)"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 offer-monitoring/0.1"
)


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


def _price(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _ean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text and text != "0" else None


def _categories(raw: dict[str, Any]) -> list[str]:
    """VTEX returns ``/Mercearia/Biscoitos/.../`` — keep leaf..root, trimmed."""
    values = []
    for path in raw.get("categories") or []:
        value = str(path).strip("/")
        if value:
            values.append(value)
    # The API lists leaf first; the persistence layer folds the list anyway.
    return values


def _default_offer(item: dict[str, Any]) -> dict[str, Any]:
    sellers = item.get("sellers") or []
    seller = next((value for value in sellers if value.get("sellerDefault")), None)
    seller = seller or (sellers[0] if sellers else {})
    return seller.get("commertialOffer") or {}


def parse_products(raw: dict[str, Any]) -> list[PaguemProduct]:
    """Map one VTEX product into one PaguemProduct per SKU (item)."""
    products: list[PaguemProduct] = []
    brand = (str(raw.get("brand") or "").strip()) or None
    categories = _categories(raw)
    slug = raw.get("linkText")
    for item in raw.get("items") or []:
        offer = _default_offer(item)
        if not offer.get("IsAvailable", True):
            continue
        sales_price = _price(offer.get("Price")) or _price(offer.get("PriceWithTaxes"))
        regular_price = _price(offer.get("ListPrice")) or sales_price
        if sales_price is None:
            continue
        if regular_price is not None and regular_price < sales_price:
            regular_price = sales_price
        name = str(
            item.get("nameComplete") or item.get("name") or raw.get("productName") or ""
        ).strip()
        if not name:
            continue
        images = item.get("images") or []
        quantity = offer.get("AvailableQuantity")
        products.append(
            PaguemProduct(
                id=str(item.get("itemId")),
                name=name,
                brand=brand,
                categories=categories,
                available=True,
                stock=float(quantity) if quantity is not None else None,
                regular_price=regular_price,
                sales_price=sales_price,
                discount=(
                    max(0.0, regular_price - sales_price)
                    if regular_price is not None
                    else None
                ),
                image_url=(images[0].get("imageUrl") if images else None),
                product_url=f"{BASE_URL}/{slug}/p" if slug else None,
                measure=item.get("measurementUnit"),
                ean=_ean(item.get("ean")),
                internal_code=str(raw.get("productReference") or "").strip() or str(
                    item.get("itemId")
                ),
            )
        )
    return products


def _slug(node: dict[str, Any]) -> str:
    url = str(node.get("url") or "").rstrip("/")
    return url.rsplit("/", 1)[-1] if url else ""


def _node(node: dict[str, Any], path: tuple[str, ...] = ()) -> dict[str, Any]:
    """Compact category node (id/name/slug/path + children) used by the collector.

    ``path`` is the cumulative id chain from the root: VTEX only filters by
    subcategory when the facet carries the whole path (``C:/32/72/``); a bare
    ``C:/72/`` silently returns zero products.
    """
    node_id = str(node.get("id"))
    node_path = (*path, node_id)
    return {
        "id": node_id,
        "name": node.get("name"),
        "slug": _slug(node),
        "path": list(node_path),
        "children": [_node(child, node_path) for child in (node.get("children") or [])],
    }


class PagueMenosCatalogClient:
    """Collects the Pague Menos online catalog through the VTEX catalog API."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        concurrency: int = CONCURRENCY,
        page_size: int = PAGE_SIZE,
        departments: list[str] | None = None,
    ):
        self.client = client
        self.concurrency = max(1, concurrency)
        self.page_size = max(1, min(page_size, 50))
        self.departments = departments

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": _UA,
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

    async def _get(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        # 206 is a normal answer for ranged catalog searches.
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.get(url, params=params, headers=self._headers())
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(min(10.0, 0.5 * (2**attempt)))
                continue
            if response.status_code in (200, 206):
                return response
            # 500 is common under concurrency on this account.
            if response.status_code >= 500 and attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(min(15.0, 1.5 * (2**attempt)))
                continue
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code} for {response.request.url}",
                request=response.request,
                response=response,
            )
        raise RuntimeError("unreachable")

    async def fetch_departments(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        """Top-level departments from the VTEX category tree."""
        response = await self._get(client, CATEGORY_TREE_URL)
        tree = response.json()
        departments = []
        for raw_node in tree:
            slug = _slug(raw_node)
            if not slug or slug in EXCLUDED_DEPARTMENTS:
                continue
            departments.append(_node(raw_node))
        return departments

    @staticmethod
    def _total(response: httpx.Response, fallback: int) -> int:
        match = re.search(r"/(\d+)$", response.headers.get("resources", ""))
        return int(match.group(1)) if match else fallback

    async def _range(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        category_path: list[str] | tuple[str, ...],
        start: int,
        stop: int,
    ) -> httpx.Response:
        filter_value = "C:/" + "/".join(str(part) for part in category_path) + "/"
        async with semaphore:
            return await self._get(
                client, SEARCH_URL, {"fq": filter_value, "_from": start, "_to": stop}
            )

    async def _category(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        node: dict[str, Any],
        errors: list[dict[str, str]],
        depth: int = 0,
    ) -> list[PaguemProduct]:
        """Products of a category, splitting into children if the VTEX cap hits.

        ``products/search`` refuses ``_from`` above 2500, so a department with
        more products than that would silently lose its tail. Children partition
        the parent, so querying them recovers everything.
        """
        first = await self._range(
            client, semaphore, node.get("path") or [node["id"]], 0, self.page_size - 1
        )
        first_items = first.json()
        total = self._total(first, len(first_items))
        children = node.get("children") or []

        if total > MAX_FROM + 1 and children and depth < 3:
            results = await asyncio.gather(
                *(
                    self._category(client, semaphore, child, errors, depth + 1)
                    for child in children
                ),
                return_exceptions=True,
            )
            split: list[PaguemProduct] = []
            for child, result in zip(children, results, strict=True):
                if isinstance(result, BaseException):
                    errors.append(collection_issue(f"category={child['slug']}", result))
                else:
                    split.extend(result)
            if split:
                return split
            # No child returned products: fall back to the capped parent scan.

        limit = min(total, MAX_FROM + 1)
        if total > MAX_FROM + 1:
            errors.append(
                {
                    "scope": f"department={node['slug']}",
                    "error": f"truncated at {MAX_FROM} of {total} products (VTEX _from cap)",
                }
            )

        pages = [first_items]
        node_path = node.get("path") or [node["id"]]
        starts = list(range(self.page_size, limit, self.page_size))
        if starts:
            results = await asyncio.gather(
                *(
                    self._range(
                        client, semaphore, node_path, start,
                        min(start + self.page_size - 1, limit - 1),
                    )
                    for start in starts
                ),
                return_exceptions=True,
            )
            for start, result in zip(starts, results, strict=True):
                if isinstance(result, BaseException):
                    errors.append(
                        collection_issue(f"department={node['slug']} start={start}", result)
                    )
                else:
                    pages.append(result.json())

        products: list[PaguemProduct] = []
        for values in pages:
            for raw in values:
                products.extend(parse_products(raw))
        return products

    async def _department(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        department: dict[str, Any],
    ) -> tuple[list[PaguemProduct], list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        products = await self._category(client, semaphore, department, errors)

        deduped: dict[str, PaguemProduct] = {}
        for product in products:
            existing = deduped.get(product.id)
            if existing is None:
                deduped[product.id] = product
            else:
                for category in product.categories:
                    if category not in existing.categories:
                        existing.categories.append(category)
        return list(deduped.values()), errors

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
        )
        try:
            departments = await self.fetch_departments(client)
            if self.departments:
                wanted = set(self.departments)
                departments = [d for d in departments if d["slug"] in wanted]

            semaphore = asyncio.Semaphore(self.concurrency)
            results = await asyncio.gather(
                *(self._department(client, semaphore, department) for department in departments),
                return_exceptions=True,
            )

            merged: dict[str, PaguemProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department, result in zip(departments, results, strict=True):
                if isinstance(result, BaseException):
                    collection_errors.append(
                        collection_issue(f"department={department['slug']}", result)
                    )
                    department_counts[department["slug"]] = 0
                    continue
                products, errors = result
                collection_errors.extend(errors)
                department_counts[department["slug"]] = len(products)
                for product in products:
                    existing = merged.get(product.id)
                    if existing is None:
                        merged[product.id] = product
                    else:
                        for category in product.categories:
                            if category not in existing.categories:
                                existing.categories.append(category)

            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            return {
                "retailer": "Pague Menos",
                "source": SEARCH_URL + "?fq=C:/{department}/",
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
