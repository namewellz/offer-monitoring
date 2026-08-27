from app.catalog.savegnago import parse_products


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
