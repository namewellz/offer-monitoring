from bs4 import BeautifulSoup

from app.catalog.paguemenos import parse_product
from app.catalog.taxonomy import canonical_department

FIXED_CARD = """
<div class="item-product" data-sku="67074">
  <a href="/odorizador-teste-unidade/p" class="item-image">
    <img data-src="//io.convertiez.com.br/m/superpaguemenos/shop/products/images/51138/small/x.jpg" alt="x">
  </a>
  <div class="desc">
    <span class="font-size-11 text-primary font-weight-bold">Luxcar</span>
    <h2 class="title"><a href="/odorizador-teste-unidade/p">Odorizador Teste Unidade</a></h2>
    <div class="box-prices"><div class="prices">
      <p class="unit-price"><span>R$ 15,99</span></p>
      <p class="sale-price"><strong>R$ 11,99</strong></p>
    </div></div>
  </div>
  <form method="POST" action="/odorizador-teste-unidade/p" class="product-form"
        data-json='{"item_id": 67074, "item_name": "Odorizador Teste Unidade", "item_brand": "Luxcar",
                    "item_category1": "Limpeza", "item_category2": "Produtos Automotivos",
                    "item_category3": "Aromatizador Para Carro", "price": 15.99, "discount": 4.0}'>
    <input type="hidden" value="51138" name="product">
    <input type="hidden" value="11.99" name="price">
  </form>
</div>
"""


def _card(html: str):
    return BeautifulSoup(html, "html.parser").select_one("div.item-product")


def test_parse_paguem_fixed_price_product() -> None:
    product = parse_product(_card(FIXED_CARD), None)

    assert product is not None
    assert product.id == "67074"
    assert product.name == "Odorizador Teste Unidade"
    assert product.brand == "Luxcar"
    assert product.categories == ["Limpeza", "Produtos Automotivos", "Aromatizador Para Carro"]
    assert product.regular_price == 15.99
    assert product.sales_price == 11.99
    assert product.discount == 4.0
    assert product.available is True
    assert product.image_url.startswith("https://io.convertiez.com.br/m/superpaguemenos/")
    assert product.product_url.endswith("/odorizador-teste-unidade/p")
    assert product.internal_code == "67074"
    assert canonical_department(product.categories, product.name) == "Limpeza"


def test_parse_paguem_skips_out_of_stock_card() -> None:
    # Out-of-stock cards have no buyable product-form (they only show an
    # "Avise-me" control) - strip the form entirely.
    start = FIXED_CARD.index("<form ")
    end = FIXED_CARD.index("</form>") + len("</form>")
    html = FIXED_CARD[:start] + "<button>Avise-me</button>" + FIXED_CARD[end:]
    assert parse_product(_card(html), None) is None


def test_parse_paguem_skips_variable_weight_card() -> None:
    weight = FIXED_CARD.replace(
        '<div class="desc">',
        '<div class="desc"><div class="pricing-weight"><p>Preço por KG: R$ 4,00</p></div>',
        1,
    )
    assert parse_product(_card(weight), None) is None


def test_parse_paguem_skips_per_gram_artifact() -> None:
    per_gram = FIXED_CARD.replace('value="11.99" name="price"', 'value="0.00399" name="price"')
    per_gram = per_gram.replace('"price": 15.99', '"price": 3.99')
    assert parse_product(_card(per_gram), None) is None
