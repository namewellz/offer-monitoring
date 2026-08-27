from decimal import Decimal

from app.catalog.persistence import price_change
from app.main import catalog_price_condition


def test_price_increase() -> None:
    amount, percent = price_change(Decimal("12.00"), Decimal("10.00"))
    assert amount == Decimal("2.00")
    assert percent == Decimal("20.0000")


def test_price_decrease() -> None:
    amount, percent = price_change(Decimal("7.50"), Decimal("10.00"))
    assert amount == Decimal("-2.50")
    assert percent == Decimal("-25.0000")


def test_first_price_has_no_change() -> None:
    assert price_change(Decimal("10.00"), None) == (None, None)


def test_catalog_final_price_condition() -> None:
    assert catalog_price_condition([]) == ("Preço final", "final")
    assert catalog_price_condition([{"minimum_quantity": 1, "price": 8.99}]) == (
        "Preço final",
        "final",
    )


def test_catalog_quantity_price_condition_lists_all_tiers() -> None:
    label, condition_type = catalog_price_condition(
        [
            {"minimum_quantity": 6, "price": 8.49},
            {"minimum_quantity": 3, "price": 8.99},
        ]
    )
    assert condition_type == "quantity"
    assert label == "Por quantidade — A partir de 3 un.: R$ 8,99 · A partir de 6 un.: R$ 8,49"


def test_catalog_wholesale_price_condition() -> None:
    label, condition_type = catalog_price_condition(
        [{"minimum_quantity": 1, "price": 15.99, "condition": "wholesale"}]
    )
    assert condition_type == "wholesale"
    assert "Atacado: R$ 15,99" in label


def test_catalog_club_price_condition() -> None:
    label, condition_type = catalog_price_condition(
        [{"minimum_quantity": 1, "price": 7.49, "condition": "club"}]
    )
    assert condition_type == "club"
    assert label == "Preço Clube/Connect — Clube/Connect: R$ 7,49"


def test_catalog_app_and_quantity_condition() -> None:
    label, condition_type = catalog_price_condition(
        [
            {"minimum_quantity": 3, "price": 7.79, "condition": "quantity"},
            {"minimum_quantity": 3, "price": 7.01, "condition": "app"},
        ]
    )
    assert condition_type == "app+quantity"
    assert "App a partir de 3 un.: R$ 7,01" in label
    assert "A partir de 3 un.: R$ 7,79" in label
