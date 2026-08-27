from app.catalog.arena import parse_product


def test_parse_product_preserves_regular_sales_and_tier_prices() -> None:
    product = parse_product(
        {
            "id": "46159",
            "productName": "Sardinha 84g",
            "brand": "Gomes da Costa",
            "available": True,
            "ATSInCurrentStore": 249,
            "price": {
                "defaultPrice": {
                    "sales": {"value": 6.09},
                    "list": {"value": 6.45},
                    "priceDiff": {"value": 0.36},
                },
                "tiers": [
                    {"quantity": 1, "price": {"sales": {"value": 6.09}}},
                    {"quantity": 6, "price": {"sales": {"value": 5.75}}},
                ],
            },
            "images": {"large": [{"absURL": "https://example.test/image.jpg"}]},
        },
        "Mercearia",
    )

    assert product.regular_price == 6.45
    assert product.sales_price == 6.09
    assert product.discount == 0.36
    assert [(tier.minimum_quantity, tier.price) for tier in product.tier_prices] == [
        (1, 6.09),
        (6, 5.75),
    ]
