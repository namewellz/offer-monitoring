"""Add department scope to LLM classifications and category labels."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_department_scope"
down_revision: str | None = "0012_shopping_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_DEPT = "Açougue"


def upgrade() -> None:
    # llm_classifications: each verdict now belongs to one store department.
    op.add_column(
        "llm_classifications",
        sa.Column(
            "department",
            sa.String(length=40),
            server_default=DEFAULT_DEPT,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_llm_classifications_department",
        "llm_classifications",
        ["department"],
    )
    op.drop_constraint("uq_llm_product_line", "llm_classifications", type_="unique")
    op.create_unique_constraint(
        "uq_llm_product_department_line",
        "llm_classifications",
        ["source_product_id", "department", "line_key"],
    )

    # llm_category_labels: vocabulary is scoped per department.
    op.add_column(
        "llm_category_labels",
        sa.Column(
            "department",
            sa.String(length=40),
            server_default=DEFAULT_DEPT,
            nullable=False,
        ),
    )
    op.create_index(
        "ix_llm_category_labels_department",
        "llm_category_labels",
        ["department"],
    )
    op.drop_constraint(
        "llm_category_labels_label_key",
        "llm_category_labels",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_llm_category_department_label",
        "llm_category_labels",
        ["department", "label"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_llm_category_department_label",
        "llm_category_labels",
        type_="unique",
    )
    op.create_unique_constraint(
        "llm_category_labels_label_key",
        "llm_category_labels",
        ["label"],
    )
    op.drop_index("ix_llm_category_labels_department", table_name="llm_category_labels")
    op.drop_column("llm_category_labels", "department")

    op.drop_constraint(
        "uq_llm_product_department_line",
        "llm_classifications",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_llm_product_line",
        "llm_classifications",
        ["source_product_id", "line_key"],
    )
    op.drop_index("ix_llm_classifications_department", table_name="llm_classifications")
    op.drop_column("llm_classifications", "department")
