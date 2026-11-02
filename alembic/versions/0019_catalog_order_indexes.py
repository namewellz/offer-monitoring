"""Índices de ordenação do read model com NULLS LAST.

A migração 0018 criou ``ix_sl_offer_discount`` e ``ix_sl_change_abs`` com
``DESC`` sem especificar o posicionamento de nulos. No Postgres ``DESC`` implica
``NULLS FIRST``, enquanto a tela ordena ``DESC NULLS LAST`` — o planejador não
consegue reaproveitar a ordem do índice e cai para *bitmap scan + sort* de todas
as linhas que casam o filtro (62 mil ofertas), em vez de ler só as 100 da página.

Revision ID: 0019_catalog_order_indexes
Revises: 0018_catalog_read_model
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_catalog_order_indexes"
down_revision: str | None = "0018_catalog_read_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '20s'")
    op.execute("DROP INDEX IF EXISTS ix_sl_offer_discount")
    op.execute(
        "CREATE INDEX ix_sl_offer_discount ON store_listings "
        "((regular_price_cents - effective_price_cents) DESC NULLS LAST, product_name) "
        "WHERE active AND is_offer"
    )
    op.execute("DROP INDEX IF EXISTS ix_sl_change_abs")
    op.execute(
        "CREATE INDEX ix_sl_change_abs ON store_listings "
        "((abs(change_percent)) DESC NULLS LAST, product_name) "
        "WHERE active AND change_percent IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sl_offer_discount")
    op.execute(
        "CREATE INDEX ix_sl_offer_discount ON store_listings "
        "((regular_price_cents - effective_price_cents) DESC, product_name) "
        "WHERE active AND is_offer"
    )
    op.execute("DROP INDEX IF EXISTS ix_sl_change_abs")
    op.execute(
        "CREATE INDEX ix_sl_change_abs ON store_listings "
        "((abs(change_percent)) DESC, product_name) "
        "WHERE active AND change_percent IS NOT NULL"
    )
