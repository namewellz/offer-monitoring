"""Add shopping lists + items (manual shopping list builder)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_shopping_lists"
down_revision: str | None = "0010_llm_category_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
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
    op.create_table(
        "shopping_list_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "list_id",
            sa.BigInteger(),
            sa.ForeignKey("shopping_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=160), nullable=False),
        sa.Column("form", sa.String(length=40), nullable=False),
        sa.Column("retailer_slug", sa.String(length=80), nullable=True),
        sa.Column("qty", sa.Numeric(10, 3), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("list_id", "category", "form", name="uq_sli_line"),
    )
    op.create_index("ix_shopping_list_items_list_id", "shopping_list_items", ["list_id"])


def downgrade() -> None:
    op.drop_index("ix_shopping_list_items_list_id", table_name="shopping_list_items")
    op.drop_table("shopping_list_items")
    op.drop_table("shopping_lists")
