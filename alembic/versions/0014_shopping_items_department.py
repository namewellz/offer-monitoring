"""Add department scope to shopping list items (multi-department lists)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_shopping_items_department"
down_revision: str | None = "0013_department_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shopping_list_items",
        sa.Column(
            "department",
            sa.String(length=40),
            server_default="Açougue",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_shopping_list_items_department",
        "shopping_list_items",
        ["department"],
    )
    op.drop_constraint("uq_sli_line", "shopping_list_items", type_="unique")
    op.create_unique_constraint(
        "uq_sli_line",
        "shopping_list_items",
        ["list_id", "department", "category", "form"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sli_line", "shopping_list_items", type_="unique")
    op.create_unique_constraint(
        "uq_sli_line",
        "shopping_list_items",
        ["list_id", "category", "form"],
    )
    op.drop_index("ix_shopping_list_items_department", table_name="shopping_list_items")
    op.drop_column("shopping_list_items", "department")
