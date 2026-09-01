from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.catalog.arena import ArenaProduct, TierPrice
from app.catalog.resilience import collection_issue, collection_metadata, require_products

GRAPHQL_URL = "https://fed-gateway.mercafacil.com/graphql"
STORE_ID = "2"
STORE_SLUG = "hortolandia"
DEPARTMENTS = {
    "1": "HORTIFRUTIGRANJEIRO",
    "2": "AÇOUGUE",
    "3": "MERCEARIA",
    "4": "FRIOS E LATICÍNIOS",
    "5": "PADARIA",
    "6": "SWIFT",
    "7": "PET SHOP",
    "8": "PEIXARIA",
    "9": "MAGAZINE",
}

PRODUCTS_QUERY = """
query ProductsByDepartment(
  $storeId: String!, $departmentId: String!, $pageSize: Int!, $page: Int!
) {
  ecommerceProducts(
    storeId: $storeId, departmentId: $departmentId,
    pageSize: $pageSize, page: $page
  ) {
    page
    records
    products {
      id modelId name slug image price priceWithDiscount quantityDescription
      discount initialWeight incrementalWeight brand stock limitSaleCart
      expirationDate department
      unitOfMeasurement { abbreviation }
      variants { id name percentage default }
      wholesale { price minimunQuantity }
      clubSale {
        minimunQuantity maximunQuantity discount price priceWithDiscount endDate
      }
    }
  }
}
"""


def parse_product(raw: dict[str, Any], category: str) -> ArenaProduct:
    regular_price = float(raw["price"]) if raw.get("price") is not None else None
    discounted = raw.get("priceWithDiscount")
    sales_price = float(discounted) if discounted and discounted > 0 else regular_price
    tiers = [
        TierPrice(int(item["minimunQuantity"]), float(item["price"]))
        for item in raw.get("wholesale") or []
        if item.get("price") is not None and item.get("minimunQuantity") is not None
    ]
    club = raw.get("clubSale") or {}
    club_price = club.get("priceWithDiscount") or club.get("price")
    if club_price is not None:
        tiers.append(
            TierPrice(
                int(club.get("minimunQuantity") or 1),
                float(club_price),
                condition="club",
            )
        )

    unit = (raw.get("unitOfMeasurement") or {}).get("abbreviation")
    model_id = str(raw.get("modelId") or raw["id"])
    return ArenaProduct(
        id=model_id,
        name=str(raw.get("name") or "").strip(),
        brand=(str(raw["brand"]).strip() if raw.get("brand") else None),
        categories=list(dict.fromkeys([category, raw.get("department")]))
        if raw.get("department")
        else [category],
        available=float(raw.get("stock") or 0) > 0,
        stock=float(raw["stock"]) if raw.get("stock") is not None else None,
        regular_price=regular_price,
        sales_price=sales_price,
        discount=float(raw["discount"]) if raw.get("discount") is not None else None,
        tier_prices=tiers,
        image_url=raw.get("image"),
        product_url=(
            f"https://www.goodbom.com.br/{STORE_SLUG}/produto/m/"
            f"{raw.get('slug')}-{model_id}"
        ),
        measure=unit,
    )


class GoodBomCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None, page_size: int = 500):
        self.client = client
        self.page_size = page_size

    async def _page(
        self, client: httpx.AsyncClient, department_id: str, page: int
    ) -> dict[str, Any]:
        response = await client.post(
            GRAPHQL_URL,
            json={
                "operationName": "ProductsByDepartment",
                "query": PRODUCTS_QUERY,
                "variables": {
                    "storeId": STORE_ID,
                    "departmentId": department_id,
                    "pageSize": self.page_size,
                    "page": page,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"GoodBom GraphQL error: {payload['errors'][0]['message']}")
        return payload["data"]["ecommerceProducts"]

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=90,
            headers={
                "Accept": "application/json",
                "User-Agent": "offer-monitoring/0.1",
                "x-custom-origin": "goodbom.com.br",
                "x-request-source": "client",
            },
        )
        try:
            merged: dict[str, ArenaProduct] = {}
            department_counts: dict[str, int] = {}
            collection_errors: list[dict[str, str]] = []
            for department_id, department_name in DEPARTMENTS.items():
                page = 1
                received = 0
                while True:
                    try:
                        result = await self._page(client, department_id, page)
                    except Exception as error:
                        collection_errors.append(
                            collection_issue(f"department={department_id} page={page}", error)
                        )
                        department_counts[department_id] = received
                        break
                    raw_products = result.get("products") or []
                    total = int(result.get("records") or 0)
                    received += len(raw_products)
                    for raw in raw_products:
                        product = parse_product(raw, department_name)
                        existing = merged.get(product.id)
                        if existing:
                            for category in product.categories:
                                if category not in existing.categories:
                                    existing.categories.append(category)
                        else:
                            merged[product.id] = product
                    if not raw_products or received >= total:
                        department_counts[department_id] = total
                        break
                    page += 1
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            require_products(products, collection_errors)
            return {
                "retailer": "GoodBom",
                "source": GRAPHQL_URL,
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": department_counts,
                "store": {
                    "name": "GoodBom Hortolândia",
                    "city": "Hortolândia",
                    "state": "SP",
                    "ecommerce_id": STORE_ID,
                    "slug": STORE_SLUG,
                },
                "product_count": len(products),
                "products": [asdict(product) for product in products],
                **collection_metadata(collection_errors),
            }
        finally:
            if owns_client:
                await client.aclose()
