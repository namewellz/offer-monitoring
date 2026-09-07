import httpx

from app.catalog.taxonomy import canonical_department
from app.catalog.vipcommerce import (
    DALBEN_STORE,
    VipCommerceCatalogClient,
)

TREE = {
    "success": True,
    "data": [
        {
            "classificacao_mercadologica_id": 1,
            "nivel": "Departamento",
            "parent_id": None,
            "descricao": "Bebidas",
            "link": "/bebidas",
            "total_ofertas": 100,
            "children": [
                {
                    "classificacao_mercadologica_id": 87,
                    "nivel": "Seção",
                    "parent_id": 1,
                    "descricao": "Cereais",
                    "link": "/bebidas/cereais",
                    "total_ofertas": 10,
                    "children": [],
                }
            ],
        }
    ],
}


def _product(pid, *, secao=87, preco="12.99", em_oferta=False, oferta=None, disponivel=True):
    row = {
        "produto_id": pid,
        "descricao": f"Produto Teste {pid}",
        "imagem": f"img-{pid}.jpg",
        "disponivel": disponivel,
        "preco": preco,
        "link": f"produto-teste-{pid}",
        "codigo_barras": f"789{pid:010d}",
        "sku": f"1D-{pid:05d}",
        "codigo_erp": pid * 10,
        "em_oferta": em_oferta,
        "oferta": oferta,
        "unidade_sigla": "UN",
        "secao_id": secao,
        "id": str(pid),
    }
    return row


def _client(store=None, **kwargs):
    return VipCommerceCatalogClient(
        store=store or dict(DALBEN_STORE), **kwargs
    )


def test_parse_vipc_product_without_offer() -> None:
    raw = _product(1, secao=87, preco="12.99")
    product = _client()._parse(
        raw, department_id=1, department_name="Bebidas",
        sections={87: (1, "Cereais")},
    )
    assert product.id == "1"
    assert product.name == "Produto Teste 1"
    assert product.categories == ["Bebidas", "Cereais"]
    assert product.regular_price == 12.99
    assert product.sales_price == 12.99
    assert product.offer_tags == []
    assert product.available is True
    assert product.ean == "7890000000001"
    assert product.measure == "UN"
    assert product.image_url.startswith("https://produto-assets-vipcommerce")
    assert product.product_url == f"https://{DALBEN_STORE['host']}/produto/1/produto-teste-1"
    assert canonical_department(product.categories, product.name) == "Bebidas"


def test_parse_vipc_product_with_offer_uses_offer_price() -> None:
    raw = _product(
        2,
        preco="12.99",
        em_oferta=True,
        oferta={
            "preco_antigo": "13.29",
            "preco_oferta": "9.99",
            "tag": "exclusivo-ecommerce",
            "nome": "Exclusivo e-commerce",
        },
    )
    product = _client()._parse(
        raw, department_id=1, department_name="Bebidas",
        sections={87: (1, "Cereais")},
    )
    assert product.regular_price == 13.29
    assert product.sales_price == 9.99
    assert product.offer_tags == ["exclusivo-ecommerce"]


def test_parse_vipc_unknown_section_falls_back_to_department() -> None:
    raw = _product(3, secao=999)
    product = _client()._parse(
        raw, department_id=1, department_name="Bebidas",
        sections={87: (1, "Cereais")},
    )
    assert product.categories == ["Bebidas"]


async def test_vipc_collect_paginates_and_merges() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/auth/loja/login"):
            return httpx.Response(200, json={"success": True, "data": "jwt-token"})
        if request.url.path.endswith("/departamentos/arvore"):
            return httpx.Response(200, json=TREE)
        assert "/classificacoes_mercadologicas/departamentos/1/produtos" in request.url.path
        page = int(request.url.params["page"])
        limit = int(request.url.params["limit"])
        if page == 1:
            data = [_product(10, secao=87), _product(11, secao=87, em_oferta=True,
                     oferta={"preco_antigo": "10.99", "preco_oferta": "8.99", "tag": "x"})]
        else:
            data = [_product(10, secao=87)]  # duplicate -> merged, not duplicated
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": data,
                "paginator": {"page": page, "items_per_page": limit,
                              "total_pages": 2, "total_items": 3},
                "isRedirect": False,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = await _client(client=client, page_size=2, department_ids=[1]).collect()

    assert catalog["retailer"] == "Dalben"
    assert catalog["store"]["name"] == "Taquaral (Campinas)"
    assert catalog["product_count"] == 2
    by_id = {p["id"]: p for p in catalog["products"]}
    assert set(by_id) == {"10", "11"}
    assert by_id["11"]["sales_price"] == 8.99
    assert by_id["11"]["regular_price"] == 10.99
    assert by_id["10"]["categories"] == ["Bebidas", "Cereais"]
    assert catalog["collection_errors"] == []
