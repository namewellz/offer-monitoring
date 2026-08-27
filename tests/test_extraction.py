from datetime import date
from pathlib import Path

from app.extraction.schemas import FlyerExtraction, PriceCondition
from app.extraction.service import is_expired, reliable_prices


def test_qwen_schema_fixture_is_valid() -> None:
    value = FlyerExtraction.model_validate_json(
        Path("tests/fixtures/qwen/valid_response.json").read_text()
    )
    assert value.offers[0].prices[0].price is not None


def test_expired_flyer_detection() -> None:
    assert is_expired(date(2026, 8, 22), date(2026, 8, 23))
    assert not is_expired(date(2026, 8, 23), date(2026, 8, 23))


def test_unsupported_duplicate_minimum_condition_is_removed() -> None:
    prices = [
        PriceCondition(type="UNIT_PRICE", price=12.99),
        PriceCondition(type="MIN_QUANTITY", price=12.99, minimum_quantity=3),
    ]
    assert reliable_prices(prices) == prices[:1]
