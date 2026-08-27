from app.catalog.davita import parse_product


def test_parse_davita_offer_preserves_public_and_connect_prices() -> None:
    product = parse_product(
        {
            "sku": 2114,
            "barcode": "7891234567890",
            "is_kg": 1,
            "catid": 50,
            "subcatid": 2,
            "name": " CUPIM BOVINO BD KG",
            "price": 53.89,
            "offer": {
                "offer_id": 307931,
                "share_link": "https://ofertas.mobilesim.com.br/?hash=test",
                "offer_price": 53.99,
                "offer_connect": 42.98,
                "offer_finish_date": "2026-08-24",
            },
        }
    )
    assert product.id == "2114"
    assert product.name == "CUPIM BOVINO BD KG"
    assert product.regular_price == 53.89
    assert product.sales_price == 53.99
    assert product.ean == "7891234567890"
    assert product.tier_prices[0].condition == "club"
    assert product.tier_prices[0].price == 42.98
    assert product.offer_tags == [
        "promotion",
        "connect-price",
        "valid-until:2026-08-24",
    ]


def test_short_davita_barcode_is_not_treated_as_ean() -> None:
    product = parse_product(
        {"sku": 1, "barcode": "2114", "name": "Produto", "price": 1, "offer": {}}
    )
    assert product.ean is None
