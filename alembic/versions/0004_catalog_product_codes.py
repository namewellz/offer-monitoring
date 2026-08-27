"""Add EAN and retailer codes to catalog products."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_catalog_product_codes"
down_revision: str | None = "0003_catalog_price_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_products", sa.Column("ean", sa.String(length=32), nullable=True))
    op.add_column("catalog_products", sa.Column("internal_code", sa.String(length=120), nullable=True))
    op.create_index("ix_catalog_products_ean", "catalog_products", ["ean"])


def downgrade() -> None:
    op.drop_index("ix_catalog_products_ean", table_name="catalog_products")
    op.drop_column("catalog_products", "internal_code")
    op.drop_column("catalog_products", "ean")
