"""Catalog collector for the VIPCommerce "Supermercado Online" platform.

Shared by stores that run the VIPCommerce (Magalu white-label supermarket)
storefront, e.g. Super Dalben (org 29) and Spani (org 67). Prices and the
department tree are served from ``services.vipcommerce.com.br`` and require an
anonymous per-domain token:

1. POST ``/api-admin/v1/org/{org}/auth/loja/login`` with
   ``{domain, username: "loja", key: <app lojaAuthJWT>}`` returns a JWT in
   ``data`` (headers ``domainkey`` + ``organizationid`` are mandatory).
2. Catalog GETs use ``Authorization: Bearer <jwt>`` plus the same
   ``domainkey`` / ``organizationid`` headers.

The store is a fulfilment unit (``filial`` + ``centro_distribuicao``); the CD
whose delivery area covers the region drives the prices seen online.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.resilience import (
    collection_issue,
    collection_metadata,
    require_products,
)

API_BASE = "https://services.vipcommerce.com.br"
ASSET_BASE = "https://produto-assets-vipcommerce-com-br.br-se1.magaluobjects.com"
IMAGE_SIZE = "250x250"
PAGE_SIZE = 1000

# Public per-app credentials embedded in each storefront bundle
# (window env ``lojaUser`` / ``lojaAuthJWT``). Not secrets: any visitor of the
# site can read them; they only identify the anonymous storefront session.
LOJA_KEY = "df072f85df9bf7dd71b6811c34bdbaa4f219d98775b56cff9dfa5f8ca1bf8469"

DALBEN_STORE = {
    "api_base": API_BASE,
    "org": "29",
    "domain": "superdalben.com.br",
    "host": "www.superdalben.com.br",
    "filial": "1",
    "centro_distribuicao": "1",
    "loja_user": "loja",
    "loja_key": LOJA_KEY,
    "retailer_name": "Dalben",
    "retailer_slug": "dalben",
    "store_name": "Taquaral (Campinas)",
    "store_city": "Campinas",
    "store_state": "SP",
    "store_postal_code": "13076-000",
    "store_latitude": "-22.87823600",
    "store_longitude": "-47.04429900",
}

# Spani runs on the VIPCommerce beta environment. Unit CD 42 (Spani Campinas 3)
# is the nearest store to Hortolândia (≈14 km).
SPANI_STORE = {
    "api_base": "https://services-beta.vipcommerce.com.br",
    "org": "67",
    "domain": "spanionline.com.br",
    "host": "www.spanionline.com.br",
    "filial": "1",
    "centro_distribuicao": "42",
    "loja_user": "loja",
    "loja_key": LOJA_KEY,
    "retailer_name": "Spani",
    "retailer_slug": "spani",
    "store_name": "Spani Campinas 3",
    "store_city": "Campinas",
    "store_state": "SP",
    "store_postal_code": "13060-080",
    "store_latitude": "-22.91446805",
    "store_longitude": "-47.10081850",
}


@dataclass
class VipcProduct:
    id: str
    name: str
    brand: str | None = None
    categories: list[str] = field(default_factory=list)
    available: bool = False
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


def _text(value: Any, maximum: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if maximum is None else text[:maximum]


class VipCommerceCatalogClient:
    """Collects the full product catalog of one VIPCommerce store unit."""

    def __init__(
        self,
        store: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
        page_size: int = PAGE_SIZE,
        department_ids: list[int] | None = None,
    ):
        self.store = store or DALBEN_STORE
        self.client = client
        self.page_size = page_size
        self.department_ids = department_ids
        self._token: str | None = None

    # -- auth ----------------------------------------------------------------
    def _base(self) -> str:
        base = self.store.get("api_base") or API_BASE
        return f"{base}/api-admin/v1/org/{self.store['org']}"

    def _headers(self, *, auth: bool = True) -> dict[str, str]:
        headers = {
            "domainkey": self.store["domain"],
            "organizationid": self.store["org"],
            "Accept": "application/json",
        }
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
            headers["sessao-id"] = "offer-monitoring"
        return headers

    async def _login(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{self._base()}/auth/loja/login",
            json={
                "domain": self.store["domain"],
                "username": self.store.get("loja_user", "loja"),
                "key": self.store["loja_key"],
            },
            headers=self._headers(auth=False),
        )
        response.raise_for_status()
        payload = response.json()
        token = (payload or {}).get("data")
        if not token:
            raise RuntimeError(
                f"VIPCommerce login returned no token: {str(payload)[:200]}"
            )
        self._token = str(token)

    # -- data ----------------------------------------------------------------
    async def _department_tree(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        response = await client.get(
            f"{self._base()}/filial/{self.store['filial']}/centro_distribuicao/"
            f"{self.store['centro_distribuicao']}/loja/classificacoes_mercadologicas/"
            "departamentos/arvore",
            headers=self._headers(),
        )
        response.raise_for_status()
        return (response.json() or {}).get("data") or []

    @staticmethod
    def _flatten_tree(tree: list[dict[str, Any]]) -> tuple[dict[int, str], dict[int, tuple[int, str]]]:
        """Return (department names, {section_id: (department_id, section)})."""
        departments: dict[int, str] = {}
        sections: dict[int, tuple[int, str]] = {}
        for node in tree or []:
            dept_id = int(node["classificacao_mercadologica_id"])
            departments[dept_id] = node.get("descricao") or ""
            for child in node.get("children") or []:
                section_id = int(child["classificacao_mercadologica_id"])
                sections[section_id] = (dept_id, child.get("descricao") or "")
        return departments, sections

    async def _department_page(
        self,
        client: httpx.AsyncClient,
        department_id: int,
        page: int,
    ) -> tuple[list[dict[str, Any]], int]:
        url = (
            f"{self._base()}/filial/{self.store['filial']}/centro_distribuicao/"
            f"{self.store['centro_distribuicao']}/loja/classificacoes_mercadologicas/"
            f"departamentos/{department_id}/produtos"
        )
        response = await client.get(
            url,
            params={"page": page, "limit": self.page_size},
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json() or {}
        data = payload.get("data") or []
        paginator = payload.get("paginator") or {}
        total_items = int(paginator.get("total_items") or len(data))
        return data, total_items

    def _parse(
        self,
        raw: dict[str, Any],
        *,
        department_id: int,
        department_name: str,
        sections: dict[int, tuple[int, str]],
    ) -> VipcProduct:
        product_id = int(raw.get("produto_id") or raw.get("id") or 0)
        offer = raw.get("oferta") or {}
        em_oferta = bool(raw.get("em_oferta")) and bool(offer)
        base = _number(raw.get("preco"))
        if em_oferta:
            sales_price = _number(offer.get("preco_oferta")) or base
            regular_price = _number(offer.get("preco_antigo")) or base
        else:
            regular_price = base
            sales_price = base

        categories = [department_name]
        section_id = raw.get("secao_id") or raw.get("classificacao_mercadologica_id")
        if section_id is not None:
            section = sections.get(int(section_id))
            if section and section[0] == department_id:
                categories.append(section[1])

        image = raw.get("imagem")
        slug = raw.get("link")
        return VipcProduct(
            id=str(product_id),
            name=str(raw.get("descricao") or "").strip(),
            brand=_text(raw.get("marca"), 160),
            categories=list(dict.fromkeys(categories)),
            available=bool(raw.get("disponivel")),
            stock=None,
            regular_price=regular_price,
            sales_price=sales_price,
            discount=None,
            image_url=(
                f"{ASSET_BASE}/{IMAGE_SIZE}/{image}" if image else None
            ),
            product_url=(
                f"https://{self.store['host']}/produto/{product_id}/{slug}"
                if slug
                else None
            ),
            measure=_text(raw.get("unidade_sigla"), 50),
            ean=_text(raw.get("codigo_barras"), 32),
            internal_code=_text(raw.get("sku"), 120)
            or _text(raw.get("codigo_erp"), 120),
            offer_tags=[offer.get("tag")] if em_oferta and offer.get("tag") else [],
        )

    # -- collect -------------------------------------------------------------
    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            headers={"User-Agent": "offer-monitoring/0.1"},
        )
        try:
            await self._login(client)
            tree = await self._department_tree(client)
            departments, sections = self._flatten_tree(tree)
            wanted = (
                {int(item) for item in self.department_ids}
                if self.department_ids is not None
                else set(departments)
            )

            merged: dict[str, VipcProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department_id in sorted(wanted):
                department_name = departments.get(department_id, f"Departamento {department_id}")
                page = 1
                received = 0
                total = 0
                while True:
                    try:
                        data, total = await self._department_page(
                            client, department_id, page
                        )
                    except Exception as error:
                        collection_errors.append(
                            collection_issue(
                                f"department={department_id} page={page}", error
                            )
                        )
                        department_counts[department_name] = received
                        break
                    for raw in data:
                        product = self._parse(
                            raw,
                            department_id=department_id,
                            department_name=department_name,
                            sections=sections,
                        )
                        existing = merged.get(product.id)
                        if existing is None:
                            merged[product.id] = product
                        else:
                            for category in product.categories:
                                if category not in existing.categories:
                                    existing.categories.append(category)
                    received += len(data)
                    if not data or received >= total or page >= 200:
                        department_counts[department_name] = max(received, total)
                        break
                    page += 1

            products = sorted(
                merged.values(), key=lambda item: (item.name.casefold(), item.id)
            )
            require_products(products, collection_errors)
            return {
                "retailer": self.store["retailer_name"],
                "source": (
                    f"{self._base()}/filial/{self.store['filial']}/centro_distribuicao/"
                    f"{self.store['centro_distribuicao']}/loja/classificacoes_"
                    "mercadologicas/departamentos/{id}/produtos"
                ),
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": department_counts,
                "store": {
                    "name": self.store["store_name"],
                    "city": self.store["store_city"],
                    "state": self.store["store_state"],
                    "postal_code": self.store.get("store_postal_code"),
                    "store_id": (
                        f"{self.store['org']}:{self.store['filial']}:"
                        f"{self.store['centro_distribuicao']}"
                    ),
                    "store_code": self.store["domain"],
                    "sales_channel": "web",
                    "domain": self.store["domain"],
                    "org": self.store["org"],
                    "filial": self.store["filial"],
                    "centro_distribuicao": self.store["centro_distribuicao"],
                },
                "product_count": len(products),
                "products": [asdict(product) for product in products],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()


class DalbenCatalogClient(VipCommerceCatalogClient):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        page_size: int = PAGE_SIZE,
        department_ids: list[int] | None = None,
    ):
        super().__init__(
            store=DALBEN_STORE, client=client, page_size=page_size,
            department_ids=department_ids,
        )


class SpaniCatalogClient(VipCommerceCatalogClient):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        page_size: int = PAGE_SIZE,
        department_ids: list[int] | None = None,
    ):
        super().__init__(
            store=SPANI_STORE, client=client, page_size=page_size,
            department_ids=department_ids,
        )
