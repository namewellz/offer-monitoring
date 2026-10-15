"""Store enrichment: tipo, bairro, codigo, regiao, rotulos de exibicao.

``stores.name`` continua sendo a chave de dedupe dos coletores e nao muda.
``display_name``/``short_label`` sao materializados por ``refresh_store_labels()``.
CEP (``postal_code``) e apenas interno: nunca entra nos rotulos.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_store_enrichment"
down_revision: str | None = "0014_shopping_items_department"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE stores
          ADD COLUMN store_type     text,
          ADD COLUMN store_code     text,
          ADD COLUMN neighborhood   text,
          ADD COLUMN address_line   text,
          ADD COLUMN postal_code    varchar(9),
          ADD COLUMN latitude       numeric(9,6),
          ADD COLUMN longitude      numeric(9,6),
          ADD COLUMN region_bucket  text,
          ADD COLUMN display_label  text,
          ADD COLUMN display_name   text,
          ADD COLUMN short_label    text,
          ADD COLUMN field_sources  jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN curated_at     timestamptz;
        ALTER TABLE stores
          ADD CONSTRAINT ck_stores_store_type
            CHECK (store_type IS NULL OR store_type IN ('loja','filial','cd','online')),
          ADD CONSTRAINT ck_stores_region_bucket
            CHECK (region_bucket IS NULL OR region_bucket IN ('campinas','fora','online'));
        CREATE INDEX ix_stores_filters
          ON stores (region_bucket, city, neighborhood, store_type) WHERE active;

        CREATE OR REPLACE FUNCTION refresh_store_labels() RETURNS integer
        LANGUAGE sql AS $$
          WITH base AS (
            SELECT s.id, r.name AS rede, s.city, s.neighborhood, s.store_type,
                   s.display_label, s.store_code,
                   count(*) OVER (PARTITION BY s.retailer_id, s.city) AS same_city
              FROM stores s JOIN retailers r ON r.id = s.retailer_id
          ), upd AS (
            UPDATE stores s SET
              display_name = concat_ws(' - ',
                  b.rede,
                  CASE WHEN b.store_type = 'online' THEN NULL ELSE b.city END,
                  CASE b.store_type WHEN 'loja' THEN 'Loja' WHEN 'filial' THEN 'Filial'
                                    WHEN 'cd' THEN 'CD' WHEN 'online' THEN 'Online' END,
                  b.neighborhood),
              short_label = CASE
                  WHEN b.store_type = 'online' THEN b.rede || ' Online'
                  WHEN b.display_label IS NOT NULL THEN b.rede || ' ' || b.display_label
                  WHEN b.same_city > 1 THEN b.rede || ' ' || b.city
                       || ' (' || coalesce(b.neighborhood, b.store_code, '?') || ')'
                  ELSE b.rede || ' ' || b.city END
              FROM base b WHERE b.id = s.id
            RETURNING 1)
          SELECT count(*)::int FROM upd;
        $$;

        CREATE OR REPLACE VIEW store_display AS
        SELECT s.id, r.slug AS retailer_slug, r.name AS rede, s.city AS cidade,
               s.neighborhood AS bairro, s.store_type AS tipo, s.store_code,
               s.region_bucket, s.active,
               coalesce(s.display_name, s.name) AS display_name,
               coalesce(s.short_label, s.name) AS short_label,
               s.field_sources
          FROM stores s JOIN retailers r ON r.id = s.retailer_id;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP VIEW IF EXISTS store_display;
        DROP FUNCTION IF EXISTS refresh_store_labels();
        DROP INDEX IF EXISTS ix_stores_filters;
        ALTER TABLE stores
          DROP CONSTRAINT IF EXISTS ck_stores_store_type,
          DROP CONSTRAINT IF EXISTS ck_stores_region_bucket,
          DROP COLUMN IF EXISTS store_type, DROP COLUMN IF EXISTS store_code,
          DROP COLUMN IF EXISTS neighborhood, DROP COLUMN IF EXISTS address_line,
          DROP COLUMN IF EXISTS postal_code, DROP COLUMN IF EXISTS latitude,
          DROP COLUMN IF EXISTS longitude, DROP COLUMN IF EXISTS region_bucket,
          DROP COLUMN IF EXISTS display_label, DROP COLUMN IF EXISTS display_name,
          DROP COLUMN IF EXISTS short_label, DROP COLUMN IF EXISTS field_sources,
          DROP COLUMN IF EXISTS curated_at;
        """
    )
