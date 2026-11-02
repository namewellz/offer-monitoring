"""Item sem estoque não tem preço de venda.

Caso real: "Macarrão sêmola Don Sapore parafuso 500 g" no Savegnago aparecia por
R$ 1,07 há dois meses. O SKU está `IsAvailable=False` desde 24/08 e a API do
Savegnago devolve `Price=0.0` / simulação `price: null`. Em algumas coletas ela
devolve um valor qualquer (1,07), que virava período de preço e nunca mais era
corrigido — cada coleta seguinte "re-confirmava" o mesmo período.
"""

from app.catalog.v2.ingest import _availability, _clear_listing_price, _should_price
from app.db.models_v2 import StoreListing


def _listing(**overrides):
    values = {
        "target_id": 1,
        "source_product_id": 10,
        "price_status": "KNOWN",
        "availability": "AVAILABLE",
    }
    values.update(overrides)
    return StoreListing(**values)


def test_prices_available_items():
    assert _should_price(_listing()) is True


def test_does_not_price_out_of_stock_items():
    assert _should_price(_listing(availability="OUT_OF_STOCK")) is False


def test_prices_retailers_that_do_not_report_availability():
    assert _should_price(_listing(availability="UNKNOWN")) is True


def test_does_not_price_items_without_price():
    assert _should_price(_listing(price_status="UNAVAILABLE")) is False
    assert _should_price(_listing(price_status="UNKNOWN")) is False


def test_clear_listing_price_resets_the_read_model():
    listing = _listing(
        regular_price_cents=107,
        effective_price_cents=107,
        best_conditional_cents=99,
        price_basis_unit="UN",
        price_terms=[{"kind": "tag", "value": "promocao"}],
        previous_cents=265,
        change_amount_cents=-158,
        is_offer=True,
        offer_kind="price_drop",
        comparison_quantity=500,
        comparison_unit="g",
        unit_price_micros=2140,
    )
    _clear_listing_price(listing)

    assert listing.regular_price_cents is None
    assert listing.effective_price_cents is None
    assert listing.best_conditional_cents is None
    assert listing.price_basis_unit is None
    assert listing.price_terms == []
    assert listing.previous_cents is None
    assert listing.change_amount_cents is None
    assert listing.change_percent is None
    assert listing.is_offer is False
    assert listing.offer_kind is None
    assert listing.unit_price_micros is None
    # o que não é preço fica intacto
    assert listing.comparison_quantity == 500
    assert listing.comparison_unit == "g"


def test_availability_maps_savegnago_flags():
    assert _availability({"available": True}) == "AVAILABLE"
    assert _availability({"available": False}) == "OUT_OF_STOCK"
    assert _availability({}) == "UNKNOWN"
