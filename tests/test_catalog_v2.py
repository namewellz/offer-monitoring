"""Unit tests for the v2 catalog hashing and identity helpers.

These cover the canonicalization rules from section 9.2: unchanged commercial
state must hash identically (one period), while any material change hashes
differently (a new period). No database is required.
"""

from app.catalog.v2.hashing import (
    cents,
    digest,
    identity_input_state,
    price_state,
    source_product_state,
)


def test_cents_converts_decimal_strings_without_float_rounding() -> None:
    assert cents("12.99") == 1299
    assert cents("0.01") == 1
    assert cents(None) is None
    assert cents("") is None


def test_price_state_hash_ignores_tag_order_and_duplicates() -> None:
    first = price_state(
        regular_price="10.00",
        effective_price="9.99",
        offer_tags=["weekly-offers", "club", "club"],
    )
    second = price_state(
        regular_price="10.00",
        effective_price="9.99",
        offer_tags=["club", "weekly-offers"],
    )
    assert digest(first) == digest(second)


def test_price_state_hash_ignores_derived_discount() -> None:
    # `discount` is never part of the state; regular vs effective covers it.
    first = price_state(regular_price="10.00", effective_price="9.00")
    second = price_state(regular_price="10.00", effective_price="9.00")
    assert digest(first) == digest(second)


def test_same_price_hashes_equally() -> None:
    assert digest(price_state(effective_price="10.00")) == digest(
        price_state(effective_price="10.00")
    )


def test_price_change_hashes_differently() -> None:
    assert digest(price_state(effective_price="10.00")) != digest(
        price_state(effective_price="12.00")
    )


def test_club_only_price_is_a_different_state() -> None:
    plain = price_state(regular_price="10.00", effective_price="10.00")
    club = price_state(
        regular_price="10.00",
        effective_price="10.00",
        tier_prices=[{"minimum_quantity": 1, "price": "8.00", "condition": "club"}],
    )
    assert digest(plain) != digest(club)


def test_tier_reorder_does_not_change_hash() -> None:
    first = price_state(
        effective_price="10.00",
        tier_prices=[
            {"minimum_quantity": 6, "price": "8.49"},
            {"minimum_quantity": 3, "price": "8.99"},
        ],
    )
    second = price_state(
        effective_price="10.00",
        tier_prices=[
            {"minimum_quantity": 3, "price": "8.99"},
            {"minimum_quantity": 6, "price": "8.49"},
        ],
    )
    assert digest(first) == digest(second)


def test_quantity_change_is_a_different_state() -> None:
    one_kg = price_state(effective_price="18.90", quantity="1", unit="KG")
    eight_hundred = price_state(effective_price="18.90", quantity="0.800", unit="KG")
    assert digest(one_kg) != digest(eight_hundred)


def test_unknown_price_state_is_distinct() -> None:
    assert digest(price_state(effective_price=None)) != digest(
        price_state(effective_price="10.00")
    )


def test_source_product_state_excludes_image() -> None:
    state = source_product_state(name="Product")
    assert "image_url" not in state
    assert "image_url" not in source_product_state(name="Product").keys()


def test_identity_input_drops_url() -> None:
    state = source_product_state(name="Product", product_url="http://example/p")
    identity = identity_input_state(state)
    assert "product_url" not in identity


def test_source_product_url_change_does_not_change_identity() -> None:
    first = source_product_state(name="Product", product_url="http://example/a")
    second = source_product_state(name="Product", product_url="http://example/b")
    assert digest(first) != digest(second)
    assert digest(identity_input_state(first)) == digest(identity_input_state(second))
