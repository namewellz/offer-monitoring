"""A promo ending is not a shelf-price increase."""

from decimal import Decimal

from app.catalog.v2.read import row_result, shelf_previous_cents


def test_promo_end_compares_with_the_previous_shelf_price():
    # estilo-dalben R$ 11,99 ended; shelf went from R$ 25,99 to R$ 27,99
    assert (
        shelf_previous_cents(
            current_cents=2799,
            regular_cents=2799,
            best_conditional=None,
            terms=[],
            previous_effective=1199,
            previous_regular=2599,
        )
        == 2599
    )


def test_a_real_shelf_change_keeps_the_previous_effective_price():
    assert (
        shelf_previous_cents(
            current_cents=2799,
            regular_cents=2799,
            best_conditional=None,
            terms=[],
            previous_effective=2599,
            previous_regular=2599,
        )
        == 2599
    )


def test_an_open_promotion_keeps_the_previous_effective_price():
    assert (
        shelf_previous_cents(
            current_cents=1199,
            regular_cents=2599,
            best_conditional=None,
            terms=[{"kind": "tag", "value": "estilo-dalben"}],
            previous_effective=2799,
            previous_regular=2799,
        )
        == 2799
    )


def test_catalog_row_hides_the_promo_spike():
    row = (
        1,  # listing
        2799,  # regular
        2799,  # effective
        None,  # conditional
        [],  # terms
        None,  # observed
        1199,  # previous effective
        10,  # product
        "ext",
        "Coxa E Sobrecoxa 1kg",
        None,
        None,
        ["Açougue"],
        "Dalben",
        "dalben",
        "Dalben - Campinas - Loja - Taquaral",
        "UN",
        2599,  # previous regular
    )
    result = row_result(row, department="Açougue")
    assert result["previous_price"] == Decimal("25.99")
    assert result["current_price"] == Decimal("27.99")
    assert result["price_condition"] == "Preço final"
    assert result["change_percent"] == Decimal("7.70")
