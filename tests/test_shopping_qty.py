from decimal import Decimal

from app.shopping.store import _qty


def test_integer_quantity_only():
    assert _qty(2) == Decimal("2")
    assert _qty(1) == Decimal("1")
    assert _qty(1.0) == Decimal("1")


def test_decimals_are_rounded_to_whole():
    assert _qty(2.5) == Decimal("3")  # arredonda meio para cima
    assert _qty(2.4) == Decimal("2")
    assert _qty(1.1) == Decimal("1")


def test_invalid_or_zero_becomes_one():
    assert _qty(0) == Decimal("1")
    assert _qty(-3) == Decimal("1")
    assert _qty("abc") == Decimal("1")
    assert _qty(None) == Decimal("1")
    assert _qty("") == Decimal("1")
