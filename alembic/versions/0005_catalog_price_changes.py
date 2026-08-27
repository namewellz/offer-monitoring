"""Store price changes against the previous observation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_catalog_price_changes"
down_revision: str | None = "0004_catalog_product_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_price_observations",
        sa.Column("previous_sales_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "catalog_price_observations",
        sa.Column("price_change_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "catalog_price_observations",
        sa.Column("price_change_percent", sa.Numeric(10, 4), nullable=True),
    )
    op.create_index(
        "ix_catalog_observation_change_percent",
        "catalog_price_observations",
        ["price_change_percent"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalog_observation_change_percent",
        table_name="catalog_price_observations",
    )
    op.drop_column("catalog_price_observations", "price_change_percent")
    op.drop_column("catalog_price_observations", "price_change_amount")
    op.drop_column("catalog_price_observations", "previous_sales_price")
