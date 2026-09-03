"""Add llm_classifications (online DeepSeek verdicts per source product)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_llm_classifications"
down_revision: str | None = "0008_catalog_v2_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_classifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_product_id", sa.BigInteger(), nullable=False),
        sa.Column("line_key", sa.String(length=80), nullable=False),
        sa.Column("retailer_slug", sa.String(length=80), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("source_product_id", "line_key", name="uq_llm_product_line"),
    )
    op.create_index(
        "ix_llm_classifications_source_product_id",
        "llm_classifications",
        ["source_product_id"],
    )
    op.create_index(
        "ix_llm_classifications_retailer_slug",
        "llm_classifications",
        ["retailer_slug"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_classifications_retailer_slug", table_name="llm_classifications")
    op.drop_index(
        "ix_llm_classifications_source_product_id",
        table_name="llm_classifications",
    )
    op.drop_table("llm_classifications")
