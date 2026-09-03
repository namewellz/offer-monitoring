"""End-to-end validation of the v2 dual-write ingest against PostgreSQL.

Runs three synthetic collections inside a single transaction and asserts the
price-period algorithm, then rolls back so no test rows persist:

  run 1  R$ 10,00 -> period 1
  run 2  R$ 10,00 -> confirmation_count 2, no new period
  run 3  R$ 12,00 -> period 2, period 1 closed

Run with: docker compose exec api python -m scripts.validate_v2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.catalog.v2.ingest import ingest_catalog_v2
from app.db.models import Retailer, Store
from app.db.models_v2 import PricePeriod, StoreListing
from app.db.session import SessionLocal


def _catalog(observed_at: datetime, regular: str, effective: str) -> dict:
    return {
        "collected_at": observed_at.isoformat(),
        "source": "https://example.test/catalog",
        "products": [
            {
                "id": "validation-1",
                "name": "Validation Product",
                "brand": "Validation",
                "categories": ["Mercearia"],
                "available": True,
                "stock": 10,
                "regular_price": regular,
                "sales_price": effective,
                "tier_prices": [],
                "offer_tags": [],
                "measure": "UN",
                "ean": None,
                "internal_code": None,
                "product_url": None,
                "image_url": None,
            }
        ],
        "collection_status": "SUCCESS",
        "collection_errors": [],
    }


def main() -> None:
    with SessionLocal() as db:
        retailer = db.scalar(select(Retailer).where(Retailer.slug == "goodbom"))
        store = db.scalar(select(Store).where(Store.retailer_id == retailer.id))
        assert retailer is not None

        base = datetime.now(UTC).replace(microsecond=0)
        run1 = ingest_catalog_v2(
            db, _catalog(base, "10.00", "10.00"), retailer=retailer, store=store
        )
        run2 = ingest_catalog_v2(
            db,
            _catalog(base + timedelta(hours=1), "10.00", "10.00"),
            retailer=retailer,
            store=store,
        )
        run3 = ingest_catalog_v2(
            db,
            _catalog(base + timedelta(hours=2), "12.00", "12.00"),
            retailer=retailer,
            store=store,
        )

        listing = db.scalar(
            select(StoreListing).where(StoreListing.target_id == run1.target_id)
        )
        periods = db.scalars(
            select(PricePeriod)
            .where(PricePeriod.store_listing_id == listing.id)
            .order_by(PricePeriod.version)
        ).all()

        assert len(periods) == 2, [p.version for p in periods]
        assert periods[0].effective_price_cents == 1000
        assert periods[0].confirmation_count == 2
        assert periods[0].ended_at is not None
        assert periods[1].effective_price_cents == 1200
        assert periods[1].confirmation_count == 1
        assert periods[1].ended_at is None
        assert run1.items_new == 1 and run1.price_periods_created == 1
        assert run2.items_unchanged == 1 and run2.price_periods_created == 0
        assert run3.items_unchanged == 1 and run3.price_periods_created == 1

        print("periods:", [(p.version, p.effective_price_cents, p.confirmation_count) for p in periods])
        print("v2 dual-write validation OK")
        db.rollback()


if __name__ == "__main__":
    main()
