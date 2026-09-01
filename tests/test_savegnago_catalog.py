import asyncio

import httpx

from app.catalog.savegnago import SavegnagoCatalogClient, parse_products


def test_parse_savegnago_weekly_offer() -> None:
    products = parse_products(
        {
            "brand": "MARCA",
            "linkText": "produto-teste",
            "productReferenceCode": "123",
            "categories": ["/Mercearia/"],
            "items": [
                {
                    "itemId": "456",
                    "nameComplete": "Produto teste 1kg",
                    "ean": "7891234567890",
                    "measurementUnit": "UN",
                    "images": [],
                    "sellers": [
                        {
                            "sellerDefault": True,
                            "commertialOffer": {
                                "Price": 8.0,
                                "ListPrice": 10.0,
                                "AvailableQuantity": 4,
                                "IsAvailable": True,
                            },
                        }
                    ],
                }
            ],
        },
        weekly_offer=True,
    )
    product = products[0]
    assert product.id == "456"
    assert product.ean == "7891234567890"
    assert product.sales_price == 8.0
    assert product.regular_price == 10.0
    assert product.offer_tags == ["weekly-offers"]


async def test_savegnago_query_keeps_other_pages_after_transient_failure() -> None:
    collector = SavegnagoCatalogClient(concurrency=2)

    async def request(_client, params):
        start = params["_from"]
        if start == 50:
            raise httpx.HTTPStatusError(
                "temporary failure",
                request=httpx.Request("GET", "https://example.test/page/2"),
                response=httpx.Response(500),
            )
        return httpx.Response(
            206,
            headers={"resources": f"{start}-{start + 49}/120"},
            json=[{"page": start // 50 + 1}],
            request=httpx.Request("GET", "https://example.test/catalog"),
        )

    collector._request = request
    total, products, errors = await collector._query(None, asyncio.Semaphore(2), "C:/1/")

    assert total == 120
    assert products == [{"page": 1}, {"page": 3}]
    assert errors[0]["scope"] == "filter=C:/1/ start=50"
