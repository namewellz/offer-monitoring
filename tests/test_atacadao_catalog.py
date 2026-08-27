from app.catalog.atacadao import _leaf_categories, _price, parse_products


def test_parse_atacadao_sku_and_price() -> None:
    products = parse_products(
        {
            "productName": "Produto teste",
            "brand": "Marca",
            "linkText": "produto-teste",
            "productReferenceCode": "ABC123",
            "categories": ["/Mercearia/Massas/", "/Mercearia/"],
            "items": [{
                "itemId": "987", "nameComplete": "Produto teste 500g",
                "ean": "7891234567890", "measurementUnit": "UND",
                "images": [{"imageUrl": "https://example.test/image.jpg"}],
                "sellers": [{"sellerDefault": True, "commertialOffer": {
                    "ListPrice": 12.99, "Price": 9.99, "AvailableQuantity": 25,
                    "IsAvailable": True,
                }}],
            }],
        }
    )
    product = products[0]
    assert product.id == "987"
    assert product.ean == "7891234567890"
    assert product.internal_code == "ABC123"
    assert product.regular_price == 12.99
    assert product.sales_price == 9.99
    assert product.discount == 3.0
    assert product.stock == 25


def test_leaf_category_paths() -> None:
    tree = [{"id": 2, "name": "Mercearia", "children": [{"id": 19, "name": "Açúcar", "children": []}]}]
    assert _leaf_categories(tree) == [("C:/2/19/", "Açúcar")]


def test_vtex_prices_are_positive_and_in_cents_only_in_simulation() -> None:
    assert _price(0) is None
    assert _price(1099) == 1099.0
