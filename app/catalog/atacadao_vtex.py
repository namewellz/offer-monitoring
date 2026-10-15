"""LEGACY Atacadão collector — public VTEX catalog + checkout simulation.

Superseded by :mod:`app.catalog.atacadao`, which uses the official app's
in-store offers API (shelf price plus the app / app+card tiers, per physical
store). This module is kept because the VTEX simulation is still a genuinely
independent channel: it is useful to cross-check a branch whose app prices look
wrong, and ``scripts/compare_flyer_vs_vtex.py`` / ``scripts/probe_vtex_simulation.py``
rely on the same endpoints.

Not wired into the CLI anymore: it cannot price Americana (625), Hortolândia
(632), Indaiatuba (658) or Campinas Dunlop (677), and it never exposes the
app-only price tiers.
"""
from __future__ import annotations

import asyncio
import copy
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
SALES_CHANNEL = "1"
SIMULATION_BATCH_SIZE = 100

# Atacadão branches in the Campinas region (RMC + surroundings) whose VTEX
# seller answers the checkout simulation API. Americana (store 625) and
# Hortolândia (store 632) are excluded because their sellers do not return
# regional pricing on the public simulation endpoint.
CAMPINAS_STORES: list[dict[str, str]] = [
    {
        "name": "Atacadão Campinas Jd. Yeda",
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13060-646",
        "address": "Avenida Ruy Rodriguez, 3100 - Jardim Yeda",
        "seller": "atacadaobr662",
    },
    {
        "name": "Atacadão Campinas Dom Pedro",
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13080-395",
        "address": "Rodovia Dom Pedro I, KM 139.9 - Jardim Santa Genebra",
        "seller": "atacadaobr663",
    },
    {
        "name": "Atacadão Campinas Dunlop 24h",
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13033-050",
        "address": "Avenida Império do Sol Nascente, 100 - Jardim Aurelia",
        "seller": "atacadaobr677",
    },
    {
        "name": "Atacadão Indaiatuba",
        "city": "Indaiatuba",
        "state": "SP",
        "postal_code": "13340-600",
        "address": "Alameda Capovilla, S/N - Recreio Campestre Joia",
        "seller": "atacadaobr658",
    },
    {
        "name": "Atacadão Itu",
        "city": "Itu",
        "state": "SP",
        "postal_code": "13304-305",
        "address": "Av. Dr. Ermelindo Maffei, 945 - Brasil",
        "seller": "atacadaobr816",
    },
    {
        "name": "Atacadão Jundiaí",
        "city": "Jundiaí",
        "state": "SP",
        "postal_code": "13215-485",
        "address": "Avenida Antônio Frederico Ozanan, S/N - Jardim Liberdade",
        "seller": "atacadaobr633",
    },
    {
        "name": "Atacadão Santa Bárbara d'Oeste",
        "city": "Santa Bárbara d'Oeste",
        "state": "SP",
        "postal_code": "13454-005",
        "address": "Rua da Agricultura, 3650 - Loteamento Industrial",
        "seller": "atacadaobr948",
    },
    {
        "name": "Atacadão Sumaré",
        "city": "Sumaré",
        "state": "SP",
        "postal_code": "13175-585",
        "address": "Rod. Virgínia Viel Campos Dall'Orto, S/N - Chácara Monte Alegre",
        "seller": "atacadaobr736",
    },
]


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
        store: dict[str, str],
    ) -> list[dict[str, Any]]:
        body = {
            "items": [
                {"id": product.id, "quantity": 1, "seller": store["seller"]}
                for product in products
            ],
            "country": "BRA",
            "postalCode": store["postal_code"].replace("-", ""),
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
        self,
        client: httpx.AsyncClient,
        products: list[ArenaProduct],
        store: dict[str, str],
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
            *(self._simulation(client, semaphore, batch, store) for batch in batches),
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

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.concurrency,
                max_keepalive_connections=self.concurrency,
            ),
            headers={"Accept": "application/json", "User-Agent": "offer-monitoring/0.1"},
        )

    async def _collect_products(
        self, client: httpx.AsyncClient
    ) -> tuple[list[ArenaProduct], dict[str, int], list[dict[str, str]]]:
        """Fetch the national catalog once and merge it by product id."""
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
        products = sorted(
            merged.values(), key=lambda item: (item.name.casefold(), item.id)
        )
        require_products(products, collection_errors)
        return products, category_counts, collection_errors

    def _catalog_payload(
        self,
        store: dict[str, str],
        products: list[ArenaProduct],
        category_counts: dict[str, int],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "retailer": "Atacadão",
            "source": SEARCH_URL,
            "collected_at": datetime.now(UTC).isoformat(),
            "department_counts": category_counts,
            "store": {
                "name": store["name"],
                "city": store["city"],
                "state": store["state"],
                "postal_code": store["postal_code"],
                "address": store["address"],
                "sales_channel": SALES_CHANNEL,
                "seller": store["seller"],
            },
            "product_count": len(products),
            "products": [asdict(product) for product in products],
            **collection_metadata(errors),
        }

    async def collect_many(
        self, stores: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        """Collect one catalog per store; the national catalog is fetched once."""
        allowed = {store["seller"] for store in CAMPINAS_STORES}
        rejected = [store.get("name") for store in stores if store.get("seller") not in allowed]
        if not stores or rejected:
            raise ValueError(f"lojas fora da regiao de Campinas (legado VTEX): {rejected or 'nenhuma'}")
        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            products, category_counts, errors = await self._collect_products(client)
            catalogs: list[dict[str, Any]] = []
            for store in stores:
                store_products = copy.deepcopy(products)
                store_errors = list(errors)
                store_errors.extend(
                    await self._apply_store_prices(client, store_products, store)
                )
                catalogs.append(
                    self._catalog_payload(store, store_products, category_counts, store_errors)
                )
            return catalogs
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self) -> dict[str, Any]:
        raise ValueError("legado VTEX: loja padrao Vila Maria removida; use collect_many(CAMPINAS_STORES)")
