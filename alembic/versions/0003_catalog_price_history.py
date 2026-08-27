"""Add structured catalog products and dated price observations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_catalog_price_history"
down_revision: str | None = "0002_offer_annotations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = postgresql.ENUM(
        "PENDING", "RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED",
        name="runstatus", create_type=False,
    )
    op.create_table(
        "catalog_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        sa.Column("priced_product_count", sa.Integer(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "retailer_id", "provider_type", "source_url", "collected_at",
            name="uq_catalog_run_source_time",
        ),
    )
    op.create_table(
        "catalog_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(length=160), nullable=True),
        sa.Column("categories", postgresql.JSONB(), nullable=False),
        sa.Column("measure", sa.String(length=50), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("retailer_id", "external_id", name="uq_catalog_product_external"),
    )
    op.create_table(
        "catalog_price_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("regular_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("sales_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount", sa.Numeric(12, 2), nullable=True),
        sa.Column("tier_prices", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id"], ["catalog_products.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["catalog_runs.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "product_id", name="uq_catalog_observation_run_product"),
    )
    op.create_index(
        "ix_catalog_price_product_observed",
        "catalog_price_observations", ["product_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_price_product_observed", table_name="catalog_price_observations")
    op.drop_table("catalog_price_observations")
    op.drop_table("catalog_products")
    op.drop_table("catalog_runs")
