import httpx

from app.catalog.saovicente import SaoVicenteCatalogClient, parse_product
from app.catalog.taxonomy import canonical_department


def test_parse_saovicente_product_prices_and_local_stock() -> None:
    product = parse_product(
        {
            "id": "268089",
            "productName": "Filé de peito de frango congelado Kg",
            "brand": "Açougue",
            "available": True,
            "isActiveInCurrentStore": True,
            "ATSInCurrentStore": 24,
            "price": {
                "sales": {"value": 22.9},
                "list": {"value": 27.9},
                "priceDiff": {"value": 5.0},
                "tiers": [{"quantity": 3, "price": {"sales": {"value": 20.9}}}],
            },
            "images": {"large": [{"absURL": "https://example.test/frango.jpg"}]},
            "productShowFullUrl": "https://example.test/frango.html",
            "productMeasureValue": "weight",
        },
        "Carnes, Aves E Peixes",
    )

    assert product.id == "268089"
    assert product.stock == 24
    assert product.available is True
    assert product.regular_price == 27.9
    assert product.sales_price == 22.9
    assert product.discount == 5.0
    assert product.tier_prices[0].minimum_quantity == 3
    assert product.tier_prices[0].price == 20.9
    assert canonical_department(product.categories, product.name) == "Açougue"


async def test_saovicente_collector_selects_hortolandia_and_merges_categories() -> None:
    selected = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal selected
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        if request.url.path.endswith("Stores-CheckStock"):
            assert request.url.params["storeID"] == "018"
            selected = True
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("Stores-AvailableStores"):
            return httpx.Response(
                200,
                json={"stores": [{"storeId": "018", "storeName": "Hortolândia", "active": True}]},
            )
        assert selected
        return httpx.Response(
            200,
            json={
                "productSearch": {"count": 1},
                "productsSearchResult": [
                    {
                        "id": "1",
                        "productName": "Produto em vários departamentos",
                        "available": True,
                        "ATSInCurrentStore": 2,
                        "price": {"sales": {"value": 9.9}},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://www.svicente.com.br"
    ) as client:
        catalog = await SaoVicenteCatalogClient(client=client).collect()

    assert catalog["store"]["id"] == "018"
    assert catalog["store"]["city"] == "Hortolândia"
    assert catalog["product_count"] == 1
    assert len(catalog["products"][0]["categories"]) > 1
