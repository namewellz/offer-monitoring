"""Atacadão catalog collector backed by the official app's in-store offers API.

Why this exists
---------------
The previous implementation (kept as ``app/catalog/atacadao_vtex.py``) used the
public VTEX account (``atacadaobr.vtexcommercestable.com.br``) plus a checkout
simulation per store. That channel only ever exposed one price per item and
could not price several branches (Americana 625, Hortolândia 632, Indaiatuba
658, Campinas Dunlop 677, ...).

The "Meu Atacadão" app talks to an internal API that returns, **per physical
store**, the shelf price and the two app-only price tiers:

==================  =========================================================
``preco``           shelf price (what the printed flyer calls "PREÇO VAREJO")
``finalPrice``      price with the in-app offer (``null`` when there is none)
``finalCardPrice``  price with the in-app offer **plus** the Atacadão card
==================  =========================================================

Credentials, routes and the whole reverse-engineering process are documented in
``docs/REVERSE-ENGINEERING-APP-API.md``; a dependency-free reference client for
the same API lives in ``scripts/atacadao_app_api.py``.

Secrets come from the environment so deployments never carry them in source:

    ATACADAO_APP_BASE_URL, ATACADAO_APP_CLIENT_ID, ATACADAO_APP_CLIENT_SECRET,
    ATACADAO_APP_USERNAME, ATACADAO_APP_PASSWORD

The defaults below are the values observed in the app traffic. They are kept for
developer convenience and must be rotated into a secret manager before any
deployment that matters.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Iterable

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.catalog.resilience import collection_issue, collection_metadata, require_products
from app.catalog.taxonomy import canonical_department

BASE_URL = os.environ.get(
    "ATACADAO_APP_BASE_URL", "https://freyr.portal.atacadao.com.br"
).rstrip("/")
TOKEN_PATH = "/infosec/auth/v1/protocol/openid-connect/token"
BACKOFFICE = "/mobile/ofertas-backoffice/v1"

CLIENT_ID = os.environ.get("ATACADAO_APP_CLIENT_ID", "OfertaMobile-TokenAuth")
CLIENT_SECRET = os.environ.get(
    "ATACADAO_APP_CLIENT_SECRET", "CI4hKA5gdaXjDLm52Mz68pXOhIhiUvNA"
)
USERNAME = os.environ.get("ATACADAO_APP_USERNAME", "kcc-ofertas-externo")
PASSWORD = os.environ.get("ATACADAO_APP_PASSWORD", "WUzN!r2Jrr!8BTFteoW3J")

# The app's own User-Agent; the gateway is friendlier to it than to a bare client.
APP_UA = "Dart/3.10 (dart:io)"

# `pageSize` above 50 is rejected with
# {"status":400,"message":"pageSize deve ser no máximo 50"}.
PAGE_SIZE = 50
MAX_CONCURRENCY = 6
TOKEN_SAFETY_MARGIN = 120  # seconds; renew before the 3600 s token actually expires

DEFAULT_STORE: dict[str, Any] = {
    "name": "Atacadão Vila Maria",
    "filial": 60,
    "city": "São Paulo",
    "state": "SP",
    "postal_code": "02170-901",
    "address": "Avenida Morvan Dias de Figueiredo, 6157",
    "seller": "atacadaobr60",
}

# Atacadão branches around Campinas (RMC). Every entry is a physical store and
# the `filial` value is the store number used by the app. The list includes the
# four branches the VTEX simulation could not price: Americana, Hortolândia,
# Indaiatuba and Campinas Dunlop.
CAMPINAS_STORES: list[dict[str, Any]] = [
    {
        "name": "Atacadão Campinas Jd. Yeda",
        "filial": 662,
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13060-646",
        "address": "Avenida Ruy Rodriguez, 3100 - Jardim Yeda",
        "seller": "atacadaobr662",
    },
    {
        "name": "Atacadão Campinas Dom Pedro",
        "filial": 663,
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13080-395",
        "address": "Rodovia Dom Pedro I, KM 139.9 - Jardim Santa Genebra",
        "seller": "atacadaobr663",
    },
    {
        "name": "Atacadão Campinas Dunlop 24h",
        "filial": 677,
        "city": "Campinas",
        "state": "SP",
        "postal_code": "13033-050",
        "address": "Avenida Império do Sol Nascente, 100 - Jardim Aurelia",
        "seller": "atacadaobr677",
    },
    {
        "name": "Atacadão Hortolândia",
        "filial": 632,
        "city": "Hortolândia",
        "state": "SP",
        "postal_code": "13184-668",
        "address": "Av. Olívio Franceschini, 1333 - Parque Sao Miguel",
        "seller": None,
    },
    {
        "name": "Atacadão Americana",
        "filial": 625,
        "city": "Americana",
        "state": "SP",
        "postal_code": "13472-415",
        "address": "Rua São Gabriel, 2451 - Vila Bertini",
        "seller": None,
    },
    {
        "name": "Atacadão Indaiatuba",
        "filial": 658,
        "city": "Indaiatuba",
        "state": "SP",
        "postal_code": "13340-600",
        "address": "Alameda Capovilla, S/N - Recreio Campestre Joia",
        "seller": "atacadaobr658",
    },
    {
        "name": "Atacadão Itu",
        "filial": 816,
        "city": "Itu",
        "state": "SP",
        "postal_code": "13304-305",
        "address": "Av. Dr. Ermelindo Maffei, 945 - Brasil",
        "seller": "atacadaobr816",
    },
    {
        "name": "Atacadão Jundiaí",
        "filial": 633,
        "city": "Jundiaí",
        "state": "SP",
        "postal_code": "13215-485",
        "address": "Avenida Antônio Frederico Ozanan, S/N - Jardim Liberdade",
        "seller": "atacadaobr633",
    },
    {
        "name": "Atacadão Santa Bárbara d'Oeste",
        "filial": 948,
        "city": "Santa Bárbara d'Oeste",
        "state": "SP",
        "postal_code": "13454-005",
        "address": "Rua da Agricultura, 3650 - Loteamento Industrial",
        "seller": "atacadaobr948",
    },
    {
        "name": "Atacadão Sumaré",
        "filial": 736,
        "city": "Sumaré",
        "state": "SP",
        "postal_code": "13175-585",
        "address": "Rod. Virgínia Viel Campos Dall'Orto, S/N - Chácara Monte Alegre",
        "seller": "atacadaobr736",
    },
]

# Cities used by `atacadao-catalog --region rmc`: the collector asks the app
# which branches exist instead of relying on a hardcoded list.
REGION_CITIES: tuple[str, ...] = (
    "campinas",
    "hortolandia",
    "americana",
    "indaiatuba",
    "itu",
    "jundiai",
    "santa barbara d'oeste",
    "sumare",
    "mogi mirim",
    "piracicaba",
    "limeira",
    "rio claro",
    "araras",
    "sorocaba",
)


class AtacadaoAppError(RuntimeError):
    """Raised when the app API answers with a non-success status."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def _price(value: Any) -> float | None:
    """Parse the app's decimal prices ("6.98") into a float."""
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return round(number, 2) if number > 0 else None


def parse_app_products(
    rows: Iterable[dict[str, Any]], category: str | None = None
) -> list[ArenaProduct]:
    """Map the app's product payload onto :class:`ArenaProduct`.

    Price tiers become conditional prices so the v2 canonical state
    (``app/catalog/v2/hashing.py``) can pick the best one:

    * ``preco``          -> ``regular_price``
    * ``finalPrice``     -> ``sales_price`` + a ``condition="app"`` tier
    * ``finalCardPrice`` -> a second ``condition="app"`` tier (both are app-only
      prices, so the canonical "best conditional price" is the lowest of them)

    ``status`` is **not** stock availability: the endpoint belongs to the offers
    back office, so ``status == "DISPONIVEL"`` means "this SKU has an active offer
    right now" (and it comes with ``finalPrice``/``idOferta``/``quantityMax``),
    while a SKU with only the shelf price answers ``status == ""``. Treating that
    as availability would hide almost the whole assortment, so availability here
    is simply "the branch lists the SKU with a price".
    """
    products: list[ArenaProduct] = []
    for row in rows:
        sku = row.get("idSku")
        title = str(row.get("title") or "").strip()
        if sku is None or not title:
            continue
        shelf_price = _price(row.get("preco"))
        app_price = _price(row.get("finalPrice"))
        card_price = _price(row.get("finalCardPrice"))
        sales_price = app_price or shelf_price
        discount = None
        if shelf_price is not None and sales_price is not None:
            discount = round(max(0.0, shelf_price - sales_price), 2)

        tiers: list[TierPrice] = []
        if app_price is not None and (shelf_price is None or app_price < shelf_price):
            tiers.append(TierPrice(minimum_quantity=1, price=app_price, condition="app"))
        if card_price is not None and (app_price is None or card_price < app_price):
            tiers.append(TierPrice(minimum_quantity=1, price=card_price, condition="app"))

        tags: list[str] = []
        if app_price is not None:
            tags.append("oferta-app")
        if card_price is not None:
            tags.append("cartao-atacadao")

        leaf = str(row.get("category") or "").strip()
        # The app exposes two levels: the department it was swept by and the
        # product's own leaf category. The leaf is the most specific signal, so it
        # is what gets published; the department is only consulted when the leaf
        # alone cannot name a canonical department (otherwise the broad department
        # term would win over a specific leaf, e.g. "Bebidas" swallowing
        # "Salgadinho").
        if leaf:
            categories = [leaf]
            if category and canonical_department(categories, title) == "Outros":
                categories.append(category)
        else:
            categories = [category] if category else []

        products.append(
            ArenaProduct(
                id=str(sku),
                name=title,
                brand=None,
                categories=categories,
                available=shelf_price is not None,
                stock=None,
                regular_price=shelf_price,
                sales_price=sales_price,
                discount=discount,
                tier_prices=tiers,
                image_url=row.get("imagem") or None,
                product_url=None,
                measure=None,
                ean=str(row["ean"]).strip() if row.get("ean") else None,
                internal_code=None,
                offer_tags=tags,
            )
        )
    return products


class AtacadaoCatalogClient:
    """Collects one catalog per branch from the Meu Atacadão app API.

    The API is store-scoped: there is no national catalog endpoint, so each
    branch is swept on its own by iterating its departments. Branches are
    fetched a few at a time; concurrency is deliberately modest (``concurrency``,
    capped by :data:`MAX_CONCURRENCY`) because this is an internal API of a third
    party.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        concurrency: int = MAX_CONCURRENCY,
        base_url: str = BASE_URL,
        page_size: int = PAGE_SIZE,
    ):
        self.client = client
        self.concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
        self.base_url = base_url.rstrip("/")
        self.page_size = min(page_size, PAGE_SIZE)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.concurrency * 2,
                max_keepalive_connections=self.concurrency * 2,
            ),
            headers={"Accept": "application/json", "User-Agent": APP_UA},
        )

    async def authenticate(self) -> str:
        """Fetch (or reuse) a Keycloak access token for the app's service user."""
        async with self._token_lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            client = self.client or self._make_client()
            try:
                response = await client.post(
                    f"{self.base_url}{TOKEN_PATH}",
                    data={
                        "grant_type": "password",
                        "username": USERNAME,
                        "password": PASSWORD,
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            finally:
                if self.client is None:
                    await client.aclose()
            if response.status_code != 200:
                raise AtacadaoAppError(response.status_code, response.text)
            payload = response.json()
            self._token = payload["access_token"]
            expires_in = int(payload.get("expires_in") or 3600)
            self._token_expires_at = time.time() + max(60, expires_in - TOKEN_SAFETY_MARGIN)
            return self._token

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        token = await self.authenticate()
        url = f"{self.base_url}{path}"
        for attempt in range(4):
            try:
                response = await client.get(
                    url, params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == 3:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            if response.status_code == 401 and attempt == 0:
                # Token expired or revoked: force a new one and retry once.
                self._token = None
                self._token_expires_at = 0.0
                token = await self.authenticate()
                continue
            if response.status_code != 200:
                raise AtacadaoAppError(response.status_code, response.text)
            return response.json()
        raise RuntimeError("unreachable")

    async def _with_client(self, operation):
        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            return await operation(client)
        finally:
            if owns_client:
                await client.aclose()

    # ---------------------------------------------------------------- stores
    async def departments(self, store: int) -> list[dict[str, Any]]:
        """Top-level departments of a branch, with their offer counts."""

        async def run(client: httpx.AsyncClient) -> list[dict[str, Any]]:
            payload = await self._get(
                client, f"{BACKOFFICE}/home/categorias", {"filialId": store, "idFilial": store}
            )
            rows = payload if isinstance(payload, list) else payload.get("data") or []
            return [row for row in rows if row.get("idCategoria") is not None]

        return await self._with_client(run)

    async def find_stores(self, cities: Iterable[str], page_size: int = 50) -> list[dict[str, Any]]:
        """Ask the app which branches exist for the given cities."""

        async def run(client: httpx.AsyncClient) -> list[dict[str, Any]]:
            stores: dict[int, dict[str, Any]] = {}
            for city in cities:
                try:
                    payload = await self._get(
                        client,
                        f"{BACKOFFICE}/busca-loja-via-cidade-nome/v2",
                        {
                            "page": 1,
                            "pageSize": page_size,
                            "cityOrName": city,
                            "lat": 0.0,
                            "lon": 0.0,
                        },
                    )
                except AtacadaoAppError:
                    continue
                for row in payload.get("data") or []:
                    filial = row.get("idStore")
                    if filial is None or str(row.get("state") or "").upper() != "SP":
                        continue
                    stores[int(filial)] = {
                        "name": f"Atacadão {row.get('storeName')}".strip(),
                        "filial": int(filial),
                        "city": row.get("city"),
                        "state": row.get("state"),
                        "postal_code": row.get("zipCode"),
                        "address": ", ".join(
                            str(part)
                            for part in (row.get("address"), row.get("number"), row.get("neighborhood"))
                            if part
                        ),
                        "seller": row.get("vtexSellerId"),
                    }
            return [stores[key] for key in sorted(stores)]

        return await self._with_client(run)

    # -------------------------------------------------------------- products
    async def _department_products(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        store: int,
        department: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        identifier = department["idCategoria"]
        label = str(department.get("category") or identifier)
        errors: list[dict[str, str]] = []
        base_params = {
            "idCategoria": identifier,
            "pageSize": self.page_size,
            "onlyWithOffer": "false",
            "filialId": store,
            "idFilial": store,
        }

        async def page(number: int) -> dict[str, Any]:
            async with semaphore:
                return await self._get(
                    client, f"{BACKOFFICE}/produto/busca", {**base_params, "pageNumber": number}
                )

        first = await page(1)
        rows = list(first.get("Produtos") or [])
        total_pages = int(first.get("totalPages") or 1)
        if total_pages > 1:
            numbers = list(range(2, total_pages + 1))
            results = await asyncio.gather(
                *(page(number) for number in numbers), return_exceptions=True
            )
            for number, result in zip(numbers, results, strict=True):
                if isinstance(result, BaseException):
                    errors.append(
                        collection_issue(f"departamento={label} pagina={number}", result)
                    )
                else:
                    rows.extend(result.get("Produtos") or [])
        return rows, errors

    async def _collect_store(
        self, client: httpx.AsyncClient, store: dict[str, Any]
    ) -> dict[str, Any]:
        filial = int(store["filial"])
        departments = await self.departments(filial)
        semaphore = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(
            *(
                self._department_products(client, semaphore, filial, department)
                for department in departments
            ),
            return_exceptions=True,
        )

        merged: dict[str, ArenaProduct] = {}
        department_counts: dict[str, int] = {}
        errors: list[dict[str, str]] = []
        for department, result in zip(departments, results, strict=True):
            label = str(department.get("category") or department["idCategoria"])
            if isinstance(result, BaseException):
                errors.append(collection_issue(f"departamento={label}", result))
                department_counts[label] = 0
                continue
            rows, department_errors = result
            errors.extend(department_errors)
            department_counts[label] = len(rows)
            for product in parse_app_products(rows, label):
                existing = merged.get(product.id)
                if existing is None:
                    merged[product.id] = product
                    continue
                for category in product.categories:
                    if category not in existing.categories:
                        existing.categories.append(category)

        products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
        return self._catalog_payload(store, products, department_counts, errors)

    def _catalog_payload(
        self,
        store: dict[str, Any],
        products: list[ArenaProduct],
        department_counts: dict[str, int],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "retailer": "Atacadão",
            "source": f"{self.base_url}{BACKOFFICE}/produto/busca?filialId={store['filial']}",
            "collected_at": datetime.now(UTC).isoformat(),
            "department_counts": department_counts,
            "store": {
                "name": store["name"],
                "city": store.get("city"),
                "state": store.get("state"),
                "postal_code": store.get("postal_code"),
                "address": store.get("address"),
                "filial": store["filial"],
                "seller": store.get("seller"),
                # v2 `collection_targets` keys the branch by these two; without them
                # every store would collapse into the source defaults.
                "store_id": f"atacadao:{store['filial']}",
                "store_code": str(store["filial"]),
                "channel": "meu-atacadao-app",
            },
            "product_count": len(products),
            "products": [asdict(product) for product in products],
            **collection_metadata(errors),
        }

    # ------------------------------------------------------------ entrypoints
    async def collect_many(
        self, stores: list[dict[str, Any]], store_concurrency: int = 1
    ) -> list[dict[str, Any]]:
        """Collect one catalog per branch.

        Branches are walked one at a time by default so the per-catalog
        ``collected_at`` grows monotonically. The v2 ingest closes the previous
        ``source_product_version`` with the incoming timestamp, and the database
        enforces ``valid_until >= valid_from``
        (``ck_source_versions_valid_window``), so persisting catalogs out of
        observation order aborts the run. Raising ``store_concurrency`` is still
        supported: the returned list is sorted by ``collected_at`` either way.
        """
        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            await self.authenticate()
            batch_size = max(1, store_concurrency)
            catalogs: list[dict[str, Any]] = []
            for position in range(0, len(stores), batch_size):
                batch = stores[position : position + batch_size]
                results = await asyncio.gather(
                    *(self._collect_store(client, store) for store in batch),
                    return_exceptions=True,
                )
                for store, result in zip(batch, results, strict=True):
                    if isinstance(result, BaseException):
                        failed = self._catalog_payload(
                            store,
                            [],
                            {},
                            [collection_issue(f"loja={store.get('filial')}", result)],
                        )
                        require_products(failed["products"], failed["collection_errors"])
                        continue
                    require_products(result["products"], result["collection_errors"])
                    catalogs.append(result)
            catalogs.sort(key=lambda item: item["collected_at"])
            return catalogs
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self) -> dict[str, Any]:
        return (await self.collect_many([DEFAULT_STORE]))[0]

    async def collect_all(self) -> list[dict[str, Any]]:
        """Collect every branch of the Campinas region, one catalog each.

        Used by the scheduled collector: ``app/jobs/tasks.py`` prefers
        ``collect_all`` when a collector provides it. The national reference
        branch (Vila Maria) is *not* part of this set — it stays available
        through ``collect()`` and through ``atacadao-catalog --region vila-maria``.
        """
        return await self.collect_many(list(CAMPINAS_STORES))
