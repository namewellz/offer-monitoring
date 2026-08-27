from decimal import Decimal

import pytest

from app.extraction.schemas import FlyerExtraction
from app.normalization.money import parse_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R$ 15,90", Decimal("15.90")),
        ("1.234,50", Decimal("1234.50")),
        (39.99, Decimal("39.99")),
        ("0", None),
        ("x", None),
    ],
)
def test_money_parser(raw, expected) -> None:
    assert parse_money(raw) == expected


def test_condition_parser_preserves_min_quantity() -> None:
    extraction = FlyerExtraction.model_validate(
        {
            "offers": [
                {
                    "raw_product_name": "Cafe",
                    "prices": [
                        {"type": "UNIT_PRICE", "price": "17,90"},
                        {"type": "MIN_QUANTITY", "price": "15,90", "minimum_quantity": 3},
                    ],
                }
            ]
        }
    )
    prices = extraction.offers[0].prices
    assert prices[0].price == Decimal("17.90")
    assert prices[1].minimum_quantity == 3


def test_condition_parser_extracts_minimum_quantity_from_model_text() -> None:
    extraction = FlyerExtraction.model_validate(
        {
            "offers": [
                {
                    "raw_product_name": "Cafe",
                    "prices": [
                        {
                            "type": "MIN_QUANTITY",
                            "price": 15.90,
                            "minimum_quantity": "a partir de 3 unid.",
                        }
                    ],
                }
            ]
        }
    )
    assert extraction.offers[0].prices[0].minimum_quantity == 3


def test_invalid_condition_is_rejected() -> None:
    with pytest.raises(ValueError):
        FlyerExtraction.model_validate(
            {
                "offers": [
                    {"raw_product_name": "Cafe", "prices": [{"type": "UNIT_PRICE", "price": "-1"}]}
                ]
            }
        )
