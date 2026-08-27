"""Add editable offer-region annotations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_offer_annotations"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "flyer_pages",
        sa.Column("annotation_status", sa.String(length=30), nullable=False, server_default="PENDING"),
    )
    op.add_column(
        "flyer_pages", sa.Column("annotated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "offer_region_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["page_id"], ["flyer_pages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id", "sequence"),
    )


def downgrade() -> None:
    op.drop_table("offer_region_annotations")
    op.drop_column("flyer_pages", "annotated_at")
    op.drop_column("flyer_pages", "annotation_status")
