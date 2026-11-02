"""Tabela agregada da lista canônica (uma linha por produto canônico).

A tela lê ``canonical_products`` — nada de GROUP BY sobre 440k listings em tempo
de requisição. A tabela é reconstruída ao final de cada projeção.

Revision ID: 0021_canonical_products
Revises: 0020_canonical_projection
"""

from alembic import op

revision = "0021_canonical_products"
down_revision = "0020_canonical_projection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '20s'")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_products (
            identity_key VARCHAR(512) PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            department TEXT,
            coverage_group VARCHAR(2),
            comparison_unit VARCHAR(6),
            offers INTEGER NOT NULL,
            retailers INTEGER NOT NULL,
            min_unit_price_micros BIGINT,
            max_unit_price_micros BIGINT,
            refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cp_offers "
        "ON canonical_products (offers DESC, canonical_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cp_group_offers "
        "ON canonical_products (coverage_group, offers DESC)"
    )
    # Só dois índices: a reconstrução derruba e recria estes (ver
    # ``app.canonical.project.refresh_canonical_products``). Busca por nome é
    # ILIKE em ~165k linhas — seq scan responde em ~20ms e evita um GIN trgm
    # caro a cada reconstrução.


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canonical_products")
