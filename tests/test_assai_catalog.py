from app.catalog.assai import _extract_items, parse_catalog_product, parse_product


def test_parse_assai_prices_and_conditions() -> None:
    product = parse_product(
        {
            "id": 13212148,
            "ean": "7891164110697",
            "description_product": "CAR FGO EMP AUROGGETS 275G",
            "product_id": 1204774,
            "quantity": 3,
            "retail_price": 8.59,
            "wholesale_price": 7.79,
            "app_price": 7.01,
            "start_date": "2026-07-30T01:00:00.000Z",
            "end_date": "2026-08-30T23:30:00.000Z",
            "category_name": "PERECIVEL INDUSTRIALIZADO",
            "is_heavy_product": 0,
            "main_image_url": "https://example.test/product.png",
        }
    )
    assert product.id == "1204774"
    assert product.ean == "7891164110697"
    assert product.regular_price == 8.59
    assert product.sales_price == 7.01
    assert [(tier.minimum_quantity, tier.price, tier.condition) for tier in product.tier_prices] == [
        (3, 7.79, "quantity"),
        (3, 7.01, "app"),
    ]
    assert product.offer_tags == [
        "promotion",
        "authenticated-catalog",
        "valid-from:2026-07-30",
        "valid-until:2026-08-30",
    ]


def test_extract_assai_items_accepts_supported_envelopes() -> None:
    assert _extract_items({"data": [{"id": 1}]}) == [{"id": 1}]
    assert _extract_items({"data": {"content": [{"id": 2}]}}) == [{"id": 2}]
    assert _extract_items({"data": {"items": [{"id": 3}]}}) == [{"id": 3}]


def test_parse_assai_full_catalog_product() -> None:
    product = parse_catalog_product(
        {
            "description_product": "Abacaxi calda 400g",
            "brand": "Marca",
            "ean": "7896025801776",
            "product_id": 100683,
            "main_image_url": "https://example.test/100683.png",
            "retail_value": 18.35,
            "wholesale_value": 15.99,
            "has_a_price": True,
            "base_unit": "un",
        }
    )
    assert product.id == "100683"
    assert product.brand == "Marca"
    assert product.available is True
    assert product.regular_price == 18.35
    assert product.sales_price == 15.99
    assert product.tier_prices[0].condition == "wholesale"
    assert product.measure == "UN"


def test_parse_assai_product_without_current_price() -> None:
    product = parse_catalog_product(
        {
            "description_product": "Produto sem preco",
            "product_id": 1,
            "retail_value": "0",
            "wholesale_value": 0,
            "has_a_price": False,
        }
    )
    assert product.available is False
    assert product.regular_price is None
    assert product.sales_price is None
