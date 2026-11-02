"""Tests for the Pague Menos collector (VTEX catalog API).

The storefront became a VTEX FastStore SPA in Oct/2026 and the collector now
reads ``/api/catalog_system/pub/products/search`` instead of scraping HTML.
These tests pin the parts that broke silently before: the 206 status, the
``resources`` header used for pagination and the department exclusions.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from app.catalog.paguemenos import (
    EXCLUDED_DEPARTMENTS,
    PagueMenosCatalogClient,
    parse_products,
)

VTEX_PRODUCT = {
    "productId": "123",
    "productName": "Odorizador Teste Unidade",
    "brand": "Luxcar",
    "linkText": "odorizador-teste-unidade",
    "productReference": "REF-1",
    "categories": ["/Limpeza/Produtos Automotivos/Aromatizador/", "/Limpeza/"],
    "items": [
        {
            "itemId": "67074",
            "nameComplete": "Odorizador Teste Unidade 250ml",
            "ean": "7891234567890",
            "measurementUnit": "un",
            "images": [{"imageUrl": "https://io.convertiez.com.br/m/superpaguemenos/x.jpg"}],
            "sellers": [
                {
                    "sellerDefault": True,
                    "commertialOffer": {
                        "Price": 11.99,
                        "ListPrice": 15.99,
                        "IsAvailable": True,
                        "AvailableQuantity": 12,
                    },
                }
            ],
        }
    ],
}


def _clone(**offer_overrides) -> dict:
    payload = json.loads(json.dumps(VTEX_PRODUCT))
    payload["items"][0]["sellers"][0]["commertialOffer"].update(offer_overrides)
    return payload


def test_parse_vtex_product() -> None:
    (product,) = parse_products(VTEX_PRODUCT)

    assert product.id == "67074"
    assert product.name == "Odorizador Teste Unidade 250ml"
    assert product.brand == "Luxcar"
    assert product.categories == ["Limpeza/Produtos Automotivos/Aromatizador", "Limpeza"]
    assert product.regular_price == 15.99
    assert product.sales_price == 11.99
    assert round(product.discount, 2) == 4.0
    assert product.ean == "7891234567890"
    assert product.measure == "un"
    assert product.stock == 12.0
    assert product.internal_code == "REF-1"
    assert product.product_url == (
        "https://www.superpaguemenos.com.br/odorizador-teste-unidade/p"
    )


def test_parse_skips_unavailable_item() -> None:
    assert parse_products(_clone(IsAvailable=False)) == []


def test_parse_skips_item_without_price() -> None:
    assert parse_products(_clone(Price=0, PriceWithTaxes=0)) == []


def test_parse_uses_list_price_as_regular_when_missing() -> None:
    (product,) = parse_products(_clone(ListPrice=0))
    assert product.regular_price == 11.99


def _tree() -> list[dict]:
    return [
        {"id": 1, "name": "Category", "url": "https://x/category", "children": []},
        {"id": 22, "name": "Açougue", "url": "https://x/acougue", "children": [{"id": 39}]},
        {"id": 35, "name": "Hortifruti", "url": "https://x/hortifruti", "children": [{"id": 50}]},
        {"id": 27, "name": "Festivos", "url": "https://x/festivos", "children": [{"id": 46}]},
        {"id": 32, "name": "Mercearia", "url": "https://x/mercearia", "children": [{"id": 33}]},
        {"id": 36, "name": "Petshop", "url": "https://x/petshop", "children": [{"id": 37}]},
    ]


def test_departments_skip_weight_and_marketing_roots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "category/tree" in request.url.path:
            return httpx.Response(200, json=_tree())
        return httpx.Response(404)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await PagueMenosCatalogClient(client=client).fetch_departments(client)

    departments = asyncio.run(run())
    assert [item["slug"] for item in departments] == ["mercearia", "petshop"]
    assert {item["slug"] for item in departments}.isdisjoint(EXCLUDED_DEPARTMENTS)


def test_department_pagination_accepts_206_and_reads_resources_header() -> None:
    """VTEX answers 206 for ranged searches; the total lives in `resources`."""

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["_from"])
        if start == 0:
            return httpx.Response(
                206,
                json=[VTEX_PRODUCT],
                headers={"resources": "0-0/2"},
            )
        second = json.loads(json.dumps(VTEX_PRODUCT))
        second["items"][0]["itemId"] = "67075"
        return httpx.Response(206, json=[second], headers={"resources": "1-1/2"})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            catalog = PagueMenosCatalogClient(client=client, page_size=1)
            semaphore = asyncio.Semaphore(2)
            return await catalog._department(
                client, semaphore, {"id": "32", "name": "Mercearia", "slug": "mercearia"}
            )

    products, errors = asyncio.run(run())
    assert [product.id for product in products] == ["67074", "67075"]
    assert errors == []
