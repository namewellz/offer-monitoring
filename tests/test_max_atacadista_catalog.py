import httpx

from app.catalog.maxatacadista import (
    STORE_CODE,
    MaxAtacadistaCatalogClient,
    parse_product,
)
from app.catalog.taxonomy import canonical_department


def test_parse_max_product_preserves_source_codes_price_and_stock() -> None:
    product = parse_product(
        {
            "bismt": "12168",
            "ean11": "7891050001108",
            "unidade_medida": "UN",
            "descricao": "Aguardente São Francisco Garrafa 970ml   ",
            "desc_mercadologica": "SAO FRANCISCO",
            "imagem": "http://s3.amazonaws.com/muffatoimgs/400x400/7891050001108.jpg",
            "estoque": 183,
            "preco1": 32.99,
        },
        "Bebidas",
    )

    assert product.id == "12168"
    assert product.internal_code == "12168"
    assert product.ean == "7891050001108"
    assert product.name == "Aguardente São Francisco Garrafa 970ml"
    assert product.brand == "SAO FRANCISCO"
    assert product.measure == "UN"
    assert product.stock == 183
    assert product.available is True
    assert product.regular_price == 32.99
    assert product.sales_price == 32.99
    assert product.image_url.startswith("https://s3.amazonaws.com/")
    assert canonical_department(product.categories, product.name) == "Bebidas"


def test_parse_max_product_keeps_unpriced_product_and_rejects_bad_ean() -> None:
    product = parse_product(
        {
            "bismt": "99",
            "ean11": "código inválido",
            "descricao": "Sabonete teste",
            "estoque": 2,
            "preco1": None,
        },
        "Higiene e Beleza",
    )

    assert product.sales_price is None
    assert product.available is True
    assert product.ean is None
    assert canonical_department(product.categories, product.name) == "Higiene"


async def test_max_collector_paginates_and_merges_departments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/departments"):
            return httpx.Response(
                200,
                json=[
                    {"id": 2, "descricao": "Bebidas"},
                    {"id": 9, "descricao": "Mercearia"},
                ],
            )
        assert request.url.params["cod_store"] == STORE_CODE
        department = int(request.url.params["department"])
        page = int(request.url.params["page"])
        if department == 2 and page == 1:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "bismt": "10",
                            "descricao": "Cerveja teste",
                            "estoque": 5,
                            "preco1": None,
                        }
                    ],
                    "next": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "bismt": "10",
                        "descricao": "Cerveja teste",
                        "estoque": 8,
                        "preco1": 4.99,
                    }
                ],
                "next": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = await MaxAtacadistaCatalogClient(client=client).collect()

    assert catalog["retailer"] == "Max Atacadista"
    assert catalog["store"]["name"] == "Max Atacadista Campinas"
    assert catalog["store"]["reference_zip_code"] == "13184222"
    assert catalog["product_count"] == 1
    assert catalog["products"][0]["categories"] == ["Bebidas", "Mercearia"]
    assert catalog["products"][0]["sales_price"] == 4.99
    assert catalog["products"][0]["stock"] == 8


async def test_max_department_keeps_previous_pages_when_one_page_fails() -> None:
    collector = MaxAtacadistaCatalogClient(max_pages=3)

    async def page(_client, _department_id, page_number):
        if page_number == 2:
            raise httpx.HTTPStatusError(
                "temporary failure",
                request=httpx.Request("GET", "https://example.test/page/2"),
                response=httpx.Response(500),
            )
        return {
            "results": [{"bismt": str(page_number), "descricao": "Produto"}],
            "next": True,
        }

    collector._page = page
    products, errors = await collector._department(None, 2)

    assert [product["bismt"] for product in products] == ["1"]
    assert errors[0]["scope"] == "department=2 page=2"
