from app.catalog.goodbom import parse_product


def test_parse_goodbom_product_prices() -> None:
    product = parse_product(
        {
            "id": "store-product",
            "modelId": "24752",
            "name": "Produto teste",
            "slug": "produto-teste",
            "price": 18.79,
            "priceWithDiscount": 15.99,
            "discount": 15,
            "stock": 20,
            "department": "MERCEARIA",
            "unitOfMeasurement": {"abbreviation": "un"},
            "wholesale": [{"minimunQuantity": 3, "price": 14.99}],
            "clubSale": None,
        },
        "MERCEARIA",
    )

    assert product.id == "24752"
    assert product.regular_price == 18.79
    assert product.sales_price == 15.99
    assert product.tier_prices[0].minimum_quantity == 3
    assert product.tier_prices[0].price == 14.99
