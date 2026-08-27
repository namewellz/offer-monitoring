from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BASE_URL = (
    "https://www.arenaatacado.com.br/on/demandware.store/"
    "Sites-Arena-Site/pt_BR/Search-UpdateGrid"
)

# Top-level public departments. Product IDs are de-duplicated because the same
# item can be merchandised in more than one category.
DEPARTMENTS = {
    "001": "Bazar E Utilidades",
    "002": "Bebidas",
    "003": "Bebidas Alcoólicas",
    "004": "Biscoitos E Salgadinhos",
    "005": "Carnes, Aves E Peixes",
    "006": "Congelados",
    "007": "Doces E Sobremesas",
    "008": "Frios E Laticínios",
    "009": "Higiene E Beleza",
    "010": "Hortifruti",
    "011": "Limpeza",
    "012": "Mercearia",
    "014": "Mundo Pet",
    "015": "Padaria",
    "016": "Saudáveis E Orgânicos",
    "018": "Coca Cola",
}


@dataclass
class TierPrice:
    minimum_quantity: int
    price: float
    condition: str = "quantity"


@dataclass
class ArenaProduct:
    id: str
    name: str
    brand: str | None
    categories: list[str] = field(default_factory=list)
    available: bool = False
    stock: float | None = None
    regular_price: float | None = None
    sales_price: float | None = None
    discount: float | None = None
    tier_prices: list[TierPrice] = field(default_factory=list)
    image_url: str | None = None
    product_url: str | None = None
    measure: str | None = None
    ean: str | None = None
    internal_code: str | None = None
    offer_tags: list[str] = field(default_factory=list)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_product(raw: dict[str, Any], category: str) -> ArenaProduct:
    price = raw.get("price") or {}
    default = price.get("defaultPrice") or {}
    sales = default.get("sales") or {}
    listed = default.get("list") or {}
    difference = default.get("priceDiff") or {}
    tiers = []
    for tier in price.get("tiers") or []:
        tier_sales = ((tier.get("price") or {}).get("sales") or {}).get("value")
        if tier_sales is not None:
            tiers.append(TierPrice(int(tier.get("quantity") or 1), float(tier_sales)))

    images = ((raw.get("images") or {}).get("large") or [])
    image_url = images[0].get("absURL") if images else None
    sales_price = _number(sales.get("value"))
    regular_price = _number(listed.get("value")) or sales_price

    return ArenaProduct(
        id=str(raw["id"]),
        name=str(raw.get("productName") or "").strip(),
        brand=(str(raw["brand"]).strip() if raw.get("brand") else None),
        categories=[category],
        available=bool(raw.get("available")),
        stock=_number(raw.get("ATSInCurrentStore")),
        regular_price=regular_price,
        sales_price=sales_price,
        discount=_number(difference.get("value")),
        tier_prices=tiers,
        image_url=image_url,
        product_url=raw.get("productShowFullUrl"),
        measure=raw.get("productMeasureValue"),
    )


class ArenaCatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None, page_size: int = 1200):
        self.client = client
        self.page_size = page_size

    async def _department(self, client: httpx.AsyncClient, category_id: str) -> list[dict]:
        products: list[dict] = []
        start = 0
        while True:
            response = await client.get(
                BASE_URL,
                params={"cgid": category_id, "start": start, "sz": self.page_size},
            )
            response.raise_for_status()
            payload = response.json()
            page = payload.get("productsSearchResult") or []
            products.extend(page)
            total = int((payload.get("productSearch") or {}).get("count") or 0)
            if not page or len(products) >= total:
                return products
            start += len(page)

    async def collect(self) -> dict[str, Any]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "offer-monitoring/0.1"},
        )
        try:
            merged: dict[str, ArenaProduct] = {}
            department_counts: dict[str, int] = {}
            for category_id, fallback_name in DEPARTMENTS.items():
                raw_products = await self._department(client, category_id)
                department_counts[category_id] = len(raw_products)
                for raw in raw_products:
                    product = parse_product(raw, fallback_name)
                    existing = merged.get(product.id)
                    if existing:
                        if fallback_name not in existing.categories:
                            existing.categories.append(fallback_name)
                    else:
                        merged[product.id] = product
            products = sorted(merged.values(), key=lambda item: (item.name.casefold(), item.id))
            return {
                "retailer": "Arena Atacado",
                "source": BASE_URL,
                "collected_at": datetime.now(UTC).isoformat(),
                "department_counts": department_counts,
                "product_count": len(products),
                "products": [asdict(product) for product in products],
            }
        finally:
            if owns_client:
                await client.aclose()


def write_catalog(
    catalog: dict[str, Any], output: Path, prefix: str = "arena"
) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{prefix}-catalog.json"
    csv_path = output / f"{prefix}-prices.csv"
    json_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "id", "name", "brand", "categories", "available", "stock",
                "regular_price", "sales_price", "discount", "tier_prices",
                "measure", "product_url", "image_url",
                "ean", "internal_code",
                "offer_tags",
            ],
        )
        writer.writeheader()
        for product in catalog["products"]:
            row = dict(product)
            row["categories"] = " | ".join(row["categories"])
            row["tier_prices"] = json.dumps(row["tier_prices"], ensure_ascii=False)
            row["offer_tags"] = " | ".join(row["offer_tags"])
            writer.writerow(row)
    return json_path, csv_path
