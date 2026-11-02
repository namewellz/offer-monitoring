"""Projeção canônica no read model (sem LLM).

O normalizador determinístico grava ``normalized_product_versions`` (uma linha por
versão de produto). Para a tela e a comparação de preço não precisarem de join,
o resultado é **projetado** em ``store_listings``:

- ``identity_key``      — o ``match_key`` canônico (marca|núcleo|tamanho|pack)
- ``canonical_name``    — nome canônico exibível
- ``coverage_group``    — A1/A2/B1..C/R (qualidade da identidade)
- ``comparison_quantity``/``comparison_unit`` — quantidade na unidade base (g/ml/un)
- ``unit_price_micros`` — preço por unidade base em micro-reais

Com isso a lista canônica é um ``GROUP BY identity_key`` e a comparação é um
``WHERE identity_key = ... ORDER BY unit_price_micros`` — uma tabela, indexada.

Revision ID: 0020_canonical_projection
Revises: 0019_catalog_order_indexes
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_canonical_projection"
down_revision: str | None = "0019_catalog_order_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '20s'")
    op.add_column("store_listings", sa.Column("identity_key", sa.Text(), nullable=True))
    op.add_column("store_listings", sa.Column("canonical_name", sa.Text(), nullable=True))
    op.add_column(
        "store_listings", sa.Column("coverage_group", sa.String(2), nullable=True)
    )
    op.add_column(
        "store_listings",
        sa.Column("comparison_quantity", sa.Numeric(14, 3), nullable=True),
    )
    op.add_column(
        "store_listings", sa.Column("comparison_unit", sa.String(6), nullable=True)
    )
    op.add_column(
        "store_listings", sa.Column("unit_price_micros", sa.BigInteger(), nullable=True)
    )
    # Lista canônica: agrupa por identidade e ordena por preço unitário.
    op.execute(
        "CREATE INDEX ix_sl_identity_price ON store_listings "
        "(identity_key, comparison_unit, unit_price_micros) "
        "WHERE active AND identity_key IS NOT NULL"
    )
    # Filtro "só comparáveis" (A1/A2).
    op.execute(
        "CREATE INDEX ix_sl_coverage_group ON store_listings (coverage_group) "
        "WHERE active AND identity_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sl_identity_price")
    op.execute("DROP INDEX IF EXISTS ix_sl_coverage_group")
    for name in (
        "identity_key",
        "canonical_name",
        "coverage_group",
        "comparison_quantity",
        "comparison_unit",
        "unit_price_micros",
    ):
        op.drop_column("store_listings", name)
