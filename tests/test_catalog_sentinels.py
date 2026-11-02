"""Preços-sentinela de indisponibilidade não viram preço nem período."""

from app.catalog.v2.ingest import _sanitize_prices
from app.catalog.v2.registry import CATALOG_SOURCES

MAX = CATALOG_SOURCES["max-atacadista"].sentinel_cents
ASSAI = CATALOG_SOURCES["assai"].sentinel_cents
PAGUEMENOS = CATALOG_SOURCES["pague-menos"].sentinel_cents


def test_one_cent_from_max_is_dropped():
    raw = {"name": "SUCO MAGUARY 200ML UVA", "sales_price": 0.01, "regular_price": 0.01}
    cleaned = _sanitize_prices(raw, MAX)
    assert cleaned["sales_price"] is None
    assert cleaned["regular_price"] is None


def test_999_9_from_assai_is_dropped():
    raw = {
        "name": "P fgo resf seara coxa fc",
        "sales_price": 999.9,
        "regular_price": 999.9,
        "offer_tags": ["promotion"],
        "tier_prices": [{"minimum_quantity": 3, "price": 949.9}],
    }
    cleaned = _sanitize_prices(raw, ASSAI)
    assert cleaned["sales_price"] is None
    assert cleaned["offer_tags"] == []
    assert cleaned["tier_prices"] == []


def test_real_premium_price_on_pague_menos_is_kept():
    # Don Melchor custa ~R$ 999,90 de verdade; a Pague Menos não tem sentinela.
    raw = {"name": "Vinho Don Melchor", "sales_price": 999.9}
    assert _sanitize_prices(raw, PAGUEMENOS)["sales_price"] == 999.9


def test_normal_price_is_untouched_and_returns_same_object():
    raw = {"name": "Arroz 5kg", "sales_price": 24.9, "regular_price": 29.9}
    assert _sanitize_prices(raw, ASSAI) is raw


def test_price_below_floor_is_sentinel_for_every_retailer():
    raw = {"name": "item", "sales_price": 0.03}
    assert _sanitize_prices(raw, frozenset())["sales_price"] is None
