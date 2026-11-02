"""Projeção canônica: preço unitário, rótulo de unidade e SQL da lista."""

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.catalog.v2.canonical_read import COMPARABLE_GROUPS, _unit_label
from app.catalog.v2.ingest import _unit_price_micros
from app.db.models_v2 import CanonicalProduct


def test_unit_price_micros_scales_by_quantity():
    # R$ 10,00 por 1 unidade -> 10_000_000 micro-reais por unidade base
    assert _unit_price_micros(1000, 1) == 10_000_000
    # R$ 10,00 por 2 unidades = R$ 5,00/un
    assert _unit_price_micros(1000, 2) == 5_000_000
    # 1 kg representado em gramas: R$ 25,90 / 1000 g -> R$ 25,90/kg
    assert _unit_price_micros(2590, 1000) == 25_900


def test_unit_price_micros_handles_missing_quantity():
    assert _unit_price_micros(1000, None) is None
    assert _unit_price_micros(1000, 0) is None
    assert _unit_price_micros(None, 1) is None


def test_unit_label_converts_grams_and_millilitres():
    # micro-reais por grama -> reais por kg; por ml -> por L
    assert _unit_label(5_000, "g") == ("kg", 5.0)
    assert _unit_label(3_200, "ml") == ("L", 3.2)
    assert _unit_label(7_000_000, "un") == ("un", 7.0)


def test_unit_label_without_data_reads_as_dash():
    assert _unit_label(None, "g") == ("—", None)
    assert _unit_label(1_000_000, None) == ("—", None)


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_canonical_list_reads_the_aggregate_table():
    statement = (
        select(CanonicalProduct)
        .where(CanonicalProduct.coverage_group.in_(COMPARABLE_GROUPS))
        .order_by(CanonicalProduct.offers.desc(), CanonicalProduct.canonical_name)
        .limit(25)
        .offset(50)
    )
    sql = _sql(statement)
    assert "FROM canonical_products" in sql
    assert "store_listings" not in sql
    assert "ORDER BY canonical_products.offers DESC" in sql
    assert "LIMIT 25 OFFSET 50" in sql


def test_canonical_search_uses_ilike_and_department_exact_match():
    statement = select(CanonicalProduct).where(
        CanonicalProduct.canonical_name.ilike("%leite%")
    )
    sql = _sql(statement)
    assert "canonical_products.canonical_name ILIKE" in sql
    assert "leite" in sql


def test_comparable_groups_are_the_high_confidence_ones():
    assert COMPARABLE_GROUPS == ("A1", "A2")


def test_aggregate_counts_offers_per_identity_key():
    statement = select(CanonicalProduct.identity_key, func.count())
    assert "count" in _sql(statement)
