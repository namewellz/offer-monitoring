"""Read model do catálogo: store_listings denormalizado + price_periods particionado.

Três mudanças, todas derivadas do design definitivo (docs/ARQUITETURA-CATALOGO-V3.md):

1. ``source_product_versions.department`` — departamento canônico calculado uma
   única vez, na criação da versão, com a regra atual (``canonical_department``).
   O backfill dos valores existentes é feito pelo comando
   ``python -m app.cli backfill-catalog-departments`` (precisa da regra em Python).
2. ``store_listings`` vira **read model**: recebe as colunas derivadas que a tela
   filtra/exibe, para que a leitura seja uma única tabela indexada com
   ``WHERE ... ORDER BY ... LIMIT`` — sem joins e sem filtro em Python.
3. ``price_periods`` passa a ser particionada por ``HASH (store_listing_id)``.

Sobre o particionamento: ``RANGE (started_at)`` por mês, como consta na primeira
versão do documento, é incompatível com os índices únicos existentes
(``UNIQUE (store_listing_id, version)`` e o índice parcial do período aberto):
no Postgres a chave de partição precisa fazer parte de todo índice único. Como a
uniqüidade do período aberto é uma invariante do ingest, particionar por HASH do
listing preserva as duas garantias e ainda faz o histórico de um produto cair
inteiro em uma partição (um único índice em vez de N).

Revision ID: 0018_catalog_read_model
Revises: 0017_canonical_refinements
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_catalog_read_model"
down_revision: str | None = "0017_canonical_refinements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARTITIONS = 16

READ_MODEL_COLUMNS = (
    ("department", sa.Text()),
    ("product_external_id", sa.String(120)),
    ("product_name", sa.Text()),
    ("product_brand", sa.String(160)),
    ("product_gtin", sa.String(32)),
    ("product_categories", postgresql.JSONB()),
    ("retailer_name", sa.Text()),
    ("retailer_slug", sa.Text()),
    ("store_name", sa.Text()),
    ("store_region_bucket", sa.Text()),
    ("store_city", sa.Text()),
    ("store_neighborhood", sa.Text()),
    ("store_type", sa.Text()),
    ("regular_price_cents", sa.Integer()),
    ("effective_price_cents", sa.Integer()),
    ("best_conditional_cents", sa.Integer()),
    ("price_basis_unit", sa.String(20)),
    ("price_terms", postgresql.JSONB()),
    ("previous_cents", sa.Integer()),
    ("change_amount_cents", sa.Integer()),
    ("change_percent", sa.Numeric(10, 2)),
    ("is_offer", sa.Boolean()),
    ("offer_kind", sa.String(30)),
    ("last_confirmed_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    # Não bloqueia para sempre atrás de uma coleta em andamento: se o lock não
    # sair em 20s, a migração falha e o container reinicia (rollback completo).
    op.execute("SET lock_timeout = '20s'")
    op.execute("SET statement_timeout = 0")

    # --- 1. departamento derivado na versão do produto ---------------------
    op.add_column("source_product_versions", sa.Column("department", sa.Text(), nullable=True))

    # --- 2. read model em store_listings -----------------------------------
    for name, column_type in READ_MODEL_COLUMNS:
        op.add_column("store_listings", sa.Column(name, column_type, nullable=True))
    op.execute("UPDATE store_listings SET is_offer = false WHERE is_offer IS NULL")
    op.alter_column(
        "store_listings",
        "is_offer",
        nullable=False,
        server_default=sa.text("false"),
    )

    # Busca por nome (ILIKE '%...%') sem varrer a tabela.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_sl_active_name ON store_listings (product_name) WHERE active"
    )
    # Índice da tela padrão (sem filtros de loja): predicado idêntico ao da query,
    # então contagem e primeira página saem de índice (index-only / index scan).
    op.execute(
        "CREATE INDEX ix_sl_page_default ON store_listings (product_name) "
        "WHERE active AND effective_price_cents IS NOT NULL "
        "AND (store_region_bucket IS NULL OR store_region_bucket <> 'fora')"
    )
    op.execute(
        "CREATE INDEX ix_sl_active_department ON store_listings "
        "(department, is_offer, product_name) WHERE active"
    )
    op.execute(
        "CREATE INDEX ix_sl_active_retailer ON store_listings (retailer_slug, product_name) "
        "WHERE active"
    )
    op.execute(
        "CREATE INDEX ix_sl_offer_discount ON store_listings "
        "((regular_price_cents - effective_price_cents) DESC, product_name) "
        "WHERE active AND is_offer"
    )
    op.execute(
        "CREATE INDEX ix_sl_change_abs ON store_listings "
        "((abs(change_percent)) DESC, product_name) "
        "WHERE active AND change_percent IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_sl_active_name_trgm ON store_listings "
        "USING gin (product_name gin_trgm_ops) WHERE active"
    )
    op.execute(
        "CREATE INDEX ix_sl_store_filter ON store_listings "
        "(store_region_bucket, store_city, store_neighborhood, store_type) WHERE active"
    )

    # --- 3. price_periods particionada por HASH(store_listing_id) ----------
    op.execute(
        """
        CREATE TABLE price_periods_new (
            id                        bigint GENERATED BY DEFAULT AS IDENTITY,
            store_listing_id          bigint NOT NULL REFERENCES store_listings (id),
            version                   integer NOT NULL,
            started_at                timestamptz NOT NULL,
            last_confirmed_at         timestamptz NOT NULL,
            ended_at                  timestamptz,
            first_run_id              bigint NOT NULL REFERENCES collection_runs (id),
            last_run_id               bigint NOT NULL REFERENCES collection_runs (id),
            confirmation_count        bigint NOT NULL DEFAULT 1,
            currency                  varchar(3) NOT NULL DEFAULT 'BRL',
            regular_price_cents       integer,
            effective_price_cents     integer NOT NULL,
            best_conditional_price_cents integer,
            normalized_unit_price_micros bigint,
            price_basis_unit          varchar(20),
            price_terms               jsonb NOT NULL DEFAULT '[]'::jsonb,
            promotion_valid_from      timestamptz,
            promotion_valid_until     timestamptz,
            state_hash                bytea NOT NULL,
            created_at                timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT price_periods_new_pkey PRIMARY KEY (id, store_listing_id)
        ) PARTITION BY HASH (store_listing_id)
        """
    )
    for remainder in range(PARTITIONS):
        op.execute(
            f"CREATE TABLE price_periods_p{remainder:02d} "
            f"PARTITION OF price_periods_new "
            f"FOR VALUES WITH (MODULUS {PARTITIONS}, REMAINDER {remainder})"
        )
    op.execute(
        """
        INSERT INTO price_periods_new (
            id, store_listing_id, version, started_at, last_confirmed_at, ended_at,
            first_run_id, last_run_id, confirmation_count, currency,
            regular_price_cents, effective_price_cents, best_conditional_price_cents,
            normalized_unit_price_micros, price_basis_unit, price_terms,
            promotion_valid_from, promotion_valid_until, state_hash, created_at
        )
        SELECT
            id, store_listing_id, version, started_at, last_confirmed_at, ended_at,
            first_run_id, last_run_id, confirmation_count, currency,
            regular_price_cents, effective_price_cents, best_conditional_price_cents,
            normalized_unit_price_micros, price_basis_unit, price_terms,
            promotion_valid_from, promotion_valid_until, state_hash, created_at
        FROM price_periods
        """
    )
    op.execute("DROP TABLE price_periods")
    op.execute("ALTER TABLE price_periods_new RENAME TO price_periods")
    op.execute(
        "ALTER TABLE price_periods RENAME CONSTRAINT price_periods_new_pkey "
        "TO price_periods_pkey"
    )
    op.execute(
        "SELECT setval("
        "pg_get_serial_sequence('price_periods', 'id'), "
        "COALESCE((SELECT max(id) FROM price_periods), 1), "
        "(SELECT max(id) IS NOT NULL FROM price_periods)"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_price_periods_listing_ver "
        "ON price_periods (store_listing_id, version)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_price_period_open "
        "ON price_periods (store_listing_id) WHERE ended_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_price_period_history "
        "ON price_periods (store_listing_id, started_at)"
    )
    op.execute(
        "CREATE INDEX ix_price_periods_open_covering "
        "ON price_periods (store_listing_id) "
        "INCLUDE (version, regular_price_cents, effective_price_cents, "
        "best_conditional_price_cents) WHERE ended_at IS NULL"
    )

    # --- 4. backfill do read model (departamento fica para o comando Python)
    op.execute(
        """
        UPDATE store_listings sl
        SET product_external_id = sp.external_id,
            product_name        = v.raw_name,
            product_brand       = v.raw_brand,
            product_gtin        = v.raw_gtin,
            product_categories  = v.raw_categories
        FROM source_products sp
        JOIN source_product_versions v ON v.id = sp.current_version_id
        WHERE sl.source_product_id = sp.id
        """
    )
    op.execute(
        """
        UPDATE store_listings sl
        SET retailer_name        = r.name,
            retailer_slug        = r.slug,
            store_name           = COALESCE(s.display_name, s.name),
            store_region_bucket  = s.region_bucket,
            store_city           = s.city,
            store_neighborhood   = s.neighborhood,
            store_type           = s.store_type
        FROM collection_targets ct
        JOIN stores s ON s.id = ct.store_id
        JOIN catalog_sources cs ON cs.id = ct.source_id
        JOIN retailers r ON r.id = cs.retailer_id
        WHERE ct.id = sl.target_id
        """
    )
    op.execute(
        """
        UPDATE store_listings sl
        SET regular_price_cents     = p.regular_price_cents,
            effective_price_cents   = p.effective_price_cents,
            best_conditional_cents  = p.best_conditional_price_cents,
            price_basis_unit        = p.price_basis_unit,
            price_terms             = p.price_terms,
            last_confirmed_at       = p.last_confirmed_at,
            previous_cents          = b.baseline,
            change_amount_cents     = CASE
                WHEN b.baseline IS NOT NULL AND b.baseline > 0
                THEN p.effective_price_cents - b.baseline
            END,
            change_percent          = CASE
                WHEN b.baseline IS NOT NULL AND b.baseline > 0
                THEN round((p.effective_price_cents - b.baseline) * 100.0 / b.baseline, 2)
            END,
            is_offer                = (
                (p.regular_price_cents IS NOT NULL
                 AND p.effective_price_cents < p.regular_price_cents)
                OR p.best_conditional_price_cents IS NOT NULL
                OR (CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                         THEN jsonb_array_length(p.price_terms) ELSE 0 END) > 0
            ),
            offer_kind              = CASE
                WHEN p.best_conditional_price_cents IS NOT NULL THEN 'club'
                WHEN EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                             THEN p.price_terms ELSE '[]'::jsonb END
                    ) t
                    WHERE t->>'kind' = 'tier' AND t->>'condition' = 'wholesale'
                ) THEN 'wholesale'
                WHEN EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                             THEN p.price_terms ELSE '[]'::jsonb END
                    ) t
                    WHERE t->>'kind' = 'tier' AND t->>'condition' = 'app'
                ) THEN 'app'
                WHEN EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                             THEN p.price_terms ELSE '[]'::jsonb END
                    ) t
                    WHERE t->>'kind' = 'tier'
                      AND COALESCE((t->>'minimum_quantity')::int, 1) > 1
                ) THEN 'quantity'
                WHEN EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                             THEN p.price_terms ELSE '[]'::jsonb END
                    ) t
                    WHERE t->>'kind' = 'tag'
                ) THEN 'promotion'
                WHEN p.regular_price_cents IS NOT NULL
                 AND p.effective_price_cents < p.regular_price_cents
                THEN 'price_drop'
            END
        FROM price_periods p
        LEFT JOIN LATERAL (
            SELECT CASE
                WHEN p.best_conditional_price_cents IS NULL
                 AND (CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                           THEN jsonb_array_length(p.price_terms) ELSE 0 END) = 0
                 AND (p.regular_price_cents IS NULL
                      OR p.effective_price_cents = p.regular_price_cents)
                 AND prev.regular_price_cents IS NOT NULL
                 AND prev.effective_price_cents < prev.regular_price_cents
                THEN prev.regular_price_cents
                ELSE prev.effective_price_cents
            END AS baseline
            FROM price_periods prev
            WHERE prev.store_listing_id = p.store_listing_id
              AND prev.version = p.version - 1
        ) b ON TRUE
        WHERE p.store_listing_id = sl.id
          AND p.ended_at IS NULL
        """
    )


def downgrade() -> None:
    # O particionamento não volta atrás: desfazer exigiria reconstruir a tabela
    # novamente. As colunas do read model são simples de remover.
    for name, _type in reversed(READ_MODEL_COLUMNS):
        op.drop_column("store_listings", name)
    op.drop_column("source_product_versions", "department")
