import httpx

from app.catalog.taxonomy import canonical_department
from app.catalog.tenda import BRANCH_ID, TendaCatalogClient, parse_product


def test_parse_tenda_product_uses_hortolandia_stock_and_prices() -> None:
    product = parse_product(
        {
            "id": 6605,
            "sku": "000000000000959608-UN",
            "barcode": "7896224836098",
            "name": "Achocolatado em Pó 700g",
            "brand": "3 Corações",
            "price": 18.70,
            "promotion": {"price": 15.90},
            "inventory": [
                {"branchId": "12", "totalAvailable": 500},
                {"branchId": BRANCH_ID, "totalAvailable": 126},
            ],
            "wholesalePrices": [{"minQuantity": 3, "price": 14.90}],
            "promotions": [
                {"template": "DESCONTOU", "price": 12.90},
                {"template": "DESCONTOU_PLUS", "price": 11.90},
            ],
            "thumbnail": "https://example.test/product.jpg",
            "url": "https://example.test/product",
        },
        "Mercearia",
    )

    assert product.id == "6605"
    assert product.stock == 126
    assert product.available is True
    assert product.regular_price == 18.70
    assert product.sales_price == 15.90
    assert product.discount == 2.80
    assert [(tier.minimum_quantity, tier.price, tier.condition) for tier in product.tier_prices] == [
        (3, 14.90, "quantity"),
        (1, 12.90, "app"),
        (1, 11.90, "app"),
    ]
    assert product.offer_tags == ["promotion", "app:descontou", "app:descontou_plus"]
    assert product.ean == "7896224836098"
    assert product.internal_code == "000000000000959608-UN"
    assert product.measure == "UN"
    assert canonical_department(product.categories, product.name) == "Mercearia"


def test_parse_tenda_product_is_unavailable_without_local_stock() -> None:
    product = parse_product(
        {
            "id": 1,
            "name": "Sabonete teste",
            "price": 3.5,
            "inventory": [{"branchId": "12", "totalAvailable": 20}],
        },
        "Higiene e Perfumaria",
    )
    assert product.stock == 0
    assert product.available is False
    assert canonical_department(product.categories, product.name) == "Higiene"


def test_parse_tenda_product_rejects_corrupted_barcode() -> None:
    product = parse_product(
        {"id": 2, "name": "Produto", "price": 1, "barcode": "EAN anotação inválida"},
        "Mercearia",
    )
    assert product.ean is None


def test_tenda_source_departments_follow_canonical_names() -> None:
    assert canonical_department(["Carnes, Aves e Peixes"]) == "Açougue"
    assert canonical_department(["Bebê"]) == "Higiene"
    assert canonical_department(["Bomboniere"]) == "Doces e Sobremesas"
    assert canonical_department(["Pães e Bolos"]) == "Padaria"
    assert canonical_department(["Fit e Saudável"]) == "Saudáveis e Orgânicos"


async def test_tenda_collector_merges_source_departments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/departments"):
            return httpx.Response(
                200,
                json=[
                    {"id": 6, "name": "Carnes, Aves e Peixes"},
                    {"id": 4, "name": "Bebidas"},
                ],
            )
        return httpx.Response(
            200,
            json={
                "total_pages": 1,
                "products": [
                    {
                        "id": 99,
                        "name": "Produto em duas vitrines",
                        "price": 10,
                        "inventory": [{"branchId": BRANCH_ID, "totalAvailable": 2}],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = await TendaCatalogClient(client=client).collect()

    assert catalog["store"]["city"] == "Hortolândia"
    assert catalog["product_count"] == 1
    assert catalog["products"][0]["categories"] == ["Carnes, Aves e Peixes", "Bebidas"]
    assert canonical_department(
        catalog["products"][0]["categories"], catalog["products"][0]["name"]
    ) == "Açougue"


async def test_tenda_department_keeps_good_pages_when_one_page_fails() -> None:
    collector = TendaCatalogClient(max_pages=3)

    async def page(_client, _category_id, page_number):
        if page_number == 2:
            raise httpx.HTTPStatusError(
                "temporary failure",
                request=httpx.Request("GET", "https://example.test/page/2"),
                response=httpx.Response(500),
            )
        return {
            "total_pages": 3,
            "products": [{"id": page_number, "name": f"Produto {page_number}"}],
        }

    collector._page = page
    products, errors = await collector._department(None, 10)

    assert [product["id"] for product in products] == [1, 3]
    assert errors[0]["scope"] == "department=10 page=2"
