"""Read model do catálogo: derivação na escrita e query de tela em SQL."""

from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.catalog.v2.ingest import _is_offer, _offer_kind, _sync_listing_snapshot
from app.catalog.v2.read import _listing_query, listing_result
from app.db.models_v2 import PricePeriod, StoreListing


def _period(**overrides):
    values = {
        "store_listing_id": 1,
        "version": 2,
        "regular_price_cents": 2799,
        "effective_price_cents": 2799,
        "best_conditional_price_cents": None,
        "price_basis_unit": "UN",
        "price_terms": [],
        "last_confirmed_at": None,
    }
    values.update(overrides)
    return PricePeriod(**values)


def _listing(**overrides):
    values = {
        "target_id": 1,
        "source_product_id": 10,
        "active": True,
        "department": "Açougue",
        "product_name": "Coxa E Sobrecoxa 1kg",
        "product_brand": "Seara",
        "product_gtin": "7891234567890",
        "product_categories": ["Açougue"],
        "retailer_name": "Dalben",
        "retailer_slug": "dalben",
        "store_name": "Dalben - Taquaral",
        "regular_price_cents": 2799,
        "effective_price_cents": 2799,
        "best_conditional_cents": None,
        "price_terms": [],
        "previous_cents": 2599,
        "change_amount_cents": 200,
        "change_percent": Decimal("7.70"),
        "is_offer": False,
        "last_confirmed_at": None,
    }
    values.update(overrides)
    return StoreListing(**values)


def test_offer_kind_prefers_club_over_price_drop():
    assert _offer_kind(2799, 1999, 1599, []) == "club"
    assert _offer_kind(2799, 1999, None, [{"kind": "tier", "condition": "club", "cents": 1599}]) == "club"


def test_offer_kind_quantity_and_promotion():
    assert (
        _offer_kind(
            2799,
            1999,
            None,
            [{"kind": "tier", "condition": "quantity", "minimum_quantity": 3, "cents": 1999}],
        )
        == "quantity"
    )
    assert _offer_kind(2799, 1999, None, [{"kind": "tag", "value": "leve-mais"}]) == "promotion"
    assert _offer_kind(2799, 1999, None, []) == "price_drop"
    assert _offer_kind(2799, 2799, None, []) is None


def test_is_offer_covers_price_drop_conditional_and_terms():
    assert _is_offer(2799, 1999, None, []) is True
    assert _is_offer(2799, 2799, 2499, []) is True
    assert _is_offer(2799, 2799, None, [{"kind": "tag", "value": "promocao"}]) is True
    assert _is_offer(2799, 2799, None, []) is False


def test_snapshot_computes_change_against_previous_period():
    listing = _listing()
    previous = _period(version=1, regular_price_cents=2599, effective_price_cents=2599)
    current = _period(version=2, regular_price_cents=2799, effective_price_cents=2799)

    _sync_listing_snapshot(listing, current, previous, changed=True)

    assert listing.previous_cents == 2599
    assert listing.change_amount_cents == 200
    assert listing.change_percent == Decimal("7.70")
    assert listing.is_offer is False


def test_snapshot_hides_promo_spike_using_shelf_baseline():
    listing = _listing()
    previous = _period(version=1, regular_price_cents=2599, effective_price_cents=1199)
    current = _period(version=2, regular_price_cents=2799, effective_price_cents=2799)

    _sync_listing_snapshot(listing, current, previous, changed=True)

    # compara com a prateleira anterior (R$ 25,99), não com o preço promocional
    assert listing.previous_cents == 2599
    assert listing.change_percent == Decimal("7.70")


def test_snapshot_of_a_new_listing_has_no_change():
    listing = _listing()
    current = _period(version=1)

    _sync_listing_snapshot(listing, current, None, changed=True)

    assert listing.previous_cents is None
    assert listing.change_amount_cents is None
    assert listing.change_percent is None


def test_snapshot_marks_conditional_price_as_offer():
    listing = _listing()
    current = _period(
        best_conditional_price_cents=2499,
        price_terms=[{"kind": "tier", "condition": "club", "cents": 2499}],
    )

    _sync_listing_snapshot(listing, current, None, changed=True)

    assert listing.is_offer is True
    assert listing.offer_kind == "club"
    assert listing.best_conditional_cents == 2499


def test_listing_query_compiles_with_filters():
    sql = str(
        _listing_query(
            product="arroz",
            retailer="assai",
            department="Mercearia",
            direction="down",
            minimum_percent=5,
            view="changes",
        ).compile(dialect=postgresql.dialect())
    )
    assert "store_listings.department = " in sql
    assert "store_listings.is_offer IS true" not in sql
    assert "store_listings.change_percent < %(change_percent" in sql
    assert "abs(store_listings.change_percent) >=" in sql
    assert "ORDER BY abs(store_listings.change_percent) DESC NULLS LAST" in sql


def test_listing_query_offers_orders_by_discount():
    sql = str(
        _listing_query(
            product=None,
            retailer=None,
            department=None,
            direction="all",
            minimum_percent=0,
            view="offers",
        ).compile(dialect=postgresql.dialect())
    )
    assert "store_listings.is_offer IS true" in sql
    assert "store_listings.regular_price_cents - store_listings.effective_price_cents" in sql


def test_listing_result_matches_dashboard_contract():
    result = listing_result(_listing())
    assert result["product"] == "Coxa E Sobrecoxa 1kg"
    assert result["department"] == "Açougue"
    assert result["retailer"] == "Dalben"
    assert result["store"] == "Dalben - Taquaral"
    assert result["current_price"] == Decimal("27.99")
    assert result["previous_price"] == Decimal("25.99")
    assert result["change_percent"] == Decimal("7.70")
    assert result["price_condition"] == "Preço final"
