"""Regression: the previous-observation lookup must not scale with the catalogue.

The Atacadão app collector persists around 11.7k SKUs per branch and the retailer
passed 65k products, which used to make the ``catalog_price_observations`` lookup
generate one bind parameter per product and abort the whole insert with
``number of parameters must be between 0 and 65535`` (PostgreSQL wire protocol
limit). The query is now a JOIN and must keep a constant parameter count.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.catalog.persistence import previous_observations_query


def test_previous_observations_query_has_constant_parameter_count() -> None:
    query = previous_observations_query(
        retailer_id=uuid4(), store_id=uuid4(), observed_at=datetime.now(UTC)
    )
    compiled = query.compile(dialect=postgresql.dialect())
    statement = str(compiled)

    assert len(compiled.params) == 3
    assert " IN (" not in statement.upper()
    assert "JOIN catalog_products" in statement
    # `DISTINCT ON` keeps only the newest observation per product.
    assert "DISTINCT ON" in statement.upper()


def test_previous_observations_query_without_store_uses_null_store() -> None:
    compiled = previous_observations_query(
        retailer_id=uuid4(), store_id=None, observed_at=datetime.now(UTC)
    ).compile(dialect=postgresql.dialect())

    assert len(compiled.params) == 2
    assert "store_id IS NULL" in str(compiled)
