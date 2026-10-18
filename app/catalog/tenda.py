"""Tenda Atacado — coletor da API pública que o app mobile também usa.

Descoberta (ver ``docs/REVERSE-ENGINEERING-APP-API.md`` §13): o app
``com.root.tendadrive.Activities`` 10.8.2 é React Native (Expo SDK 57) com o bundle
em Hermes bytecode, mas a base da API **não está** no ``assets/index.android.bundle``
— está no código Java (``classes*.dex``): ``https://api.tendaatacado.com.br/api``.
É exatamente a mesma base que este coletor já usava na versão de site, então **não
existe "API melhor no app"** como aconteceu no Atacadão. Rotas observadas no app:

* ``/public/store/departments`` (o coletor usa)
* ``/public/store/category/{id}/products`` (o coletor usa)
* ``/public/branch/all`` e ``/public/branch/zip/{cep}`` (descoberta de loja)
* ``/public/store/category/products/newness`` (vitrine de novidades)
* ``/public/client/*``, ``/public/oauth/access-token`` (exigem login; ofertas não)

Duas consequências importantes para a coleta:

1. **Preço é da rede, não da loja.** O parâmetro ``branchId`` é ignorado e o payload
traz um único ``price`` por produto mais ``inventory[]`` com uma entrada por filial
(45 lojas). Coletar outra loja muda disponibilidade/estoque, nunca o preço — por
isso ``collect()`` continua sendo uma loja (Hortolândia, CT39) e a coleta multi-loja
fica em ``collect_region()``, que **não** usa o nome ``collect_all`` justamente para
o agendador (``app/jobs/tasks.py``) seguir coletando uma loja só.
2. **As ofertas são do app.** O campo ``promotion`` (singular) que o coletor antigo
lia não existe mais no payload; as ofertas chegam em ``promotions[]`` com
``template`` (``DESCONTOU`` = Cliente APP, ``DESCONTOU_PLUS`` = Cliente APP pagando
com o Cartão Tenda) e regra ``CARTAO_TENDA`` na ``restriction``.
"""

from __future__ import annotations

import asyncio
import unicodedata
from collections.abc import Iterable
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
BRANCHES_URL = f"{API_URL}/public/branch/all"
BRANCH_ZIP_URL = f"{API_URL}/public/branch/zip/{{zip_code}}"
NEWNESS_URL = f"{API_URL}/public/store/category/products/newness"
SOURCE_URL = "https://www.tendaatacado.com.br/"

# Mesmo CEP de referência dos outros coletores de Hortolândia. O app resolve esse
# CEP em /public/branch/zip e escolhe a CT39 - Tenda Hortolândia (id 46, 38 m).
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

# Cidades da RMC que possuem loja Tenda (descobertas em /public/branch/all).
CAMPINAS_CITIES: tuple[str, ...] = (
    "campinas",
    "hortolandia",
    "sumare",
    "indaiatuba",
    "itatiba",
    "santa barbara d'oeste",
    "vinhedo",
)
# RMC + cidades vizinhas que o restante do projeto já trata como região.
REGION_CITIES: tuple[str, ...] = CAMPINAS_CITIES + ("itu", "jundiai", "salto", "piracicaba")

# Regra que caracteriza a oferta do Cartão Tenda e o canal registrado no ingest v2.
CARD_RULE = "CARTAO_TENDA"
CHANNEL = "tenda-app"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _ean(value: Any) -> str | None:
    code = str(value or "").strip()
    return code if code.isdigit() and len(code) in {8, 12, 13, 14} else None


def _norm(value: Any) -> str:
    """Minúsculo e sem acento, para casar cidade da API com a allowlist."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().casefold()


def _local_stock(raw: dict[str, Any], branch_id: str) -> float:
    for inventory in raw.get("inventory") or []:
        if str(inventory.get("branchId")) == str(branch_id):
            return float(inventory.get("totalAvailable") or 0)
    return 0.0


def _restriction_rules(promotion: dict[str, Any]) -> set[str]:
    restriction = promotion.get("restriction") or {}
    rules = restriction.get("rules") if isinstance(restriction, dict) else None
    return {str(rule.get("type") or "").upper() for rule in rules or [] if isinstance(rule, dict)}


def _is_card_promotion(promotion: dict[str, Any]) -> bool:
    """``DESCONTOU_PLUS`` = preço do app pagando com o Cartão Tenda."""

    if _restriction_rules(promotion) & {CARD_RULE}:
        return True
    return "PLUS" in str(promotion.get("template") or "").upper()


def _app_promotions(raw: dict[str, Any]) -> tuple[list[TierPrice], list[str], list[float]]:
    """Converte ``promotions[]`` em tiers do app + tags + preços sem cartão."""

    tiers: list[TierPrice] = []
    tags: list[str] = []
    open_prices: list[float] = []
    for promotion in raw.get("promotions") or []:
        if not isinstance(promotion, dict):
            continue
        price = _number(promotion.get("price"))
        template = str(promotion.get("template") or "promocao").strip()
        tag = f"app:{template.casefold()}"
        if tag not in tags:
            tags.append(tag)
        if price is None:
            continue
        if _is_card_promotion(promotion):
            tiers.append(TierPrice(1, price, condition="app-cartao"))
        else:
            tiers.append(TierPrice(1, price, condition="app"))
            open_prices.append(price)
    return tiers, tags, open_prices


def parse_product(
    raw: dict[str, Any], category: str, branch_id: str = BRANCH_ID
) -> ArenaProduct:
    regular_price = _number(raw.get("price"))
    stock = _local_stock(raw, branch_id)

    tiers: list[TierPrice] = []
    for tier in raw.get("wholesalePrices") or []:
        price = _number(tier.get("price"))
        if price is not None:
            tiers.append(TierPrice(int(tier.get("minQuantity") or 1), price))

    offer_tags: list[str] = []
    # `promotion` (singular) é o campo da primeira geração da API; continua sendo
    # lido porque alguns endpoints antigos ainda devolvem.
    legacy = raw.get("promotion") or {}
    legacy_price = _number(legacy.get("price")) if isinstance(legacy, dict) else None
    if legacy_price is not None:
        offer_tags.append("promotion")

    app_tiers, app_tags, open_prices = _app_promotions(raw)
    for tag in app_tags:
        if tag not in offer_tags:
            offer_tags.append(tag)
    tiers.extend(app_tiers)

    # Preço de venda = menor preço do app que não exige o Cartão Tenda (o preço de
    # gôndola é o `price`); cai para o preço de gôndola quando não há oferta.
    candidates = [price for price in (legacy_price, *open_prices) if price is not None]
    sales_price = min(candidates) if candidates else regular_price

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


def _branch_from_api(row: dict[str, Any]) -> dict[str, Any]:
    """Normaliza uma filial do ``/public/branch/all`` (mesma forma do app)."""

    address = row.get("address") or {}
    name = str(row.get("name") or "").strip()
    return {
        "branch_id": str(row.get("id")),
        "code": str(row.get("code") or "").strip() or None,
        "name": f"Tenda {name}".strip(),
        "city": address.get("city"),
        "state": address.get("state"),
        "postal_code": address.get("zipCode"),
        "address": ", ".join(
            str(part)
            for part in (
                address.get("addressLine1"),
                address.get("number"),
                address.get("district"),
            )
            if part
        )
        or None,
        "latitude": address.get("latitude"),
        "longitude": address.get("longitude"),
    }


def default_store() -> dict[str, Any]:
    """Loja padrão do coletor agendado (Hortolândia, CT39 / 46)."""

    return {
        "branch_id": BRANCH_ID,
        "code": BRANCH_CODE,
        "name": STORE["name"],
        "city": STORE["city"],
        "state": STORE["state"],
        "postal_code": STORE["zip_code"],
        "address": None,
        "latitude": None,
        "longitude": None,
    }


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
        self.branch_id = str(branch_id)
        self.concurrency = concurrency
        self.max_pages = max_pages
        self.proxy_url = proxy_url
        self._semaphore = asyncio.Semaphore(concurrency)

    # ------------------------------------------------------------- plumbing
    def _make_client(self) -> httpx.AsyncClient:
        proxy_url = (
            self.proxy_url if self.proxy_url is not None else get_settings().tenda_proxy_url
        )
        client_kwargs: dict[str, Any] = {
            "timeout": 60,
            "follow_redirects": True,
            "limits": httpx.Limits(max_connections=self.concurrency),
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                # Mesmos cabeçalhos do app (okhttp + versão enviada pelo app).
                "User-Agent": "okhttp/4.12.0",
                "x-app-version": "10.8.2",
                "desktop-platform": "true",
            },
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        return httpx.AsyncClient(**client_kwargs)

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

    # --------------------------------------------------------------- stores
    async def branches(self) -> list[dict[str, Any]]:
        """Todas as filiais da rede (``/public/branch/all``, rota do app)."""

        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            payload = await self._get_json(client, BRANCHES_URL)
            return [_branch_from_api(row) for row in payload]
        finally:
            if owns_client:
                await client.aclose()

    async def resolve_zip(self, zip_code: str) -> list[dict[str, Any]]:
        """Filiais mais próximas de um CEP (mesma rota que o app usa)."""

        digits = "".join(char for char in str(zip_code) if char.isdigit())
        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            payload = await self._get_json(client, BRANCH_ZIP_URL.format(zip_code=digits))
            return [_branch_from_api(row) for row in payload]
        finally:
            if owns_client:
                await client.aclose()

    async def find_stores(self, cities: Iterable[str]) -> list[dict[str, Any]]:
        """Filiais cujo município está na lista (sem acento, case-insensitive)."""

        wanted = {_norm(city) for city in cities}
        found = [store for store in await self.branches() if _norm(store.get("city")) in wanted]
        found.sort(key=lambda store: (str(store.get("city")), int(store["branch_id"])))
        return found

    # ------------------------------------------------------------- products
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

    async def _collect_store(
        self, client: httpx.AsyncClient, store: dict[str, Any]
    ) -> dict[str, Any]:
        branch_id = str(store["branch_id"])
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
                product = parse_product(raw, category, branch_id)
                existing = merged.get(product.id)
                if existing is None:
                    merged[product.id] = product
                else:
                    for source_category in product.categories:
                        if source_category not in existing.categories:
                            existing.categories.append(source_category)

        products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
        return self._catalog_payload(store, products, department_counts, collection_errors)

    def _catalog_payload(
        self,
        store: dict[str, Any],
        products: list[ArenaProduct],
        department_counts: dict[str, int],
        errors: list[dict[str, str]],
    ) -> dict[str, Any]:
        branch_id = str(store["branch_id"])
        return {
            "retailer": "Tenda Atacado",
            "source": f"{API_URL}/public/store/departments",
            "collected_at": datetime.now(UTC).isoformat(),
            "department_counts": department_counts,
            "store": {
                "name": store["name"],
                "city": store.get("city"),
                "state": store.get("state"),
                "postal_code": store.get("postal_code"),
                "address": store.get("address"),
                "branch_id": branch_id,
                # O ingest v2 casa o `collection_target` por estas chaves.
                "store_id": f"tenda:{branch_id}",
                "store_code": store.get("code"),
                "sales_channel": CHANNEL,
                "latitude": store.get("latitude"),
                "longitude": store.get("longitude"),
            },
            "product_count": len(products),
            "products": [asdict(product) for product in products],
            **collection_metadata(errors),
        }

    # ------------------------------------------------------------ entrypoints
    async def collect_many(self, stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Um catálogo por filial, sequencial e ordenado por ``collected_at``.

        O preço é o mesmo em toda a rede, então esta rota serve para
        disponibilidade/estoque por loja. O ingest v2 fecha a versão anterior com o
        timestamp recebido e o banco exige ``valid_until >= valid_from``
        (``ck_source_versions_valid_window``), daí a ordenação explícita.
        """

        if not stores:
            raise ValueError("nenhuma filial informada")
        owns_client = self.client is None
        client = self.client or self._make_client()
        try:
            catalogs: list[dict[str, Any]] = []
            for store in stores:
                catalog = await self._collect_store(client, store)
                require_products(catalog["products"], catalog["collection_errors"])
                catalogs.append(catalog)
            catalogs.sort(key=lambda item: item["collected_at"])
            return catalogs
        finally:
            if owns_client:
                await client.aclose()

    async def collect(self) -> dict[str, Any]:
        """Catálogo da loja padrão (Hortolândia/CT39): comportamento histórico."""

        return (await self.collect_many([default_store()]))[0]

    async def collect_region(self, cities: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Coleta as filiais da região — **opt-in**, fora do agendador.

        O nome evita de propósito o protocolo ``collect_all()`` lido por
        ``app/jobs/tasks.py``: como o preço do Tenda é o mesmo em toda a rede (o
        ``branchId`` é ignorado), a coleta multi-loja multiplicaria o volume sem
        trazer preço novo, só estoque. Quem quiser isso chama pela CLI
        (``--region campinas|rmc``) ou por este método.
        """

        stores = await self.find_stores(cities or CAMPINAS_CITIES)
        return await self.collect_many(stores or [default_store()])
