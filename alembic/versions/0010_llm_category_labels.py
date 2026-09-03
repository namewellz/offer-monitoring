"""Add llm_category_labels (canonical override per LLM category)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_llm_category_labels"
down_revision: str | None = "0009_llm_classifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_category_labels",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("label", sa.String(length=160), nullable=False, unique=True),
        sa.Column("canonical", sa.String(length=160), nullable=False),
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
    )
    op.create_index(
        "ix_llm_category_labels_canonical",
        "llm_category_labels",
        ["canonical"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_category_labels_canonical", table_name="llm_category_labels")
    op.drop_table("llm_category_labels")
