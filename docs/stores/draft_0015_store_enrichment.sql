-- DRAFT 0015_store_enrichment -- NAO APLICADO. Proposta apenas.
-- Enriquecimento de lojas: Rede - Cidade - Tipo - Bairro, filtros e region_bucket.
-- Regras: stores.name continua sendo a chave de dedupe dos coletores (persistence.py
-- casa por Store.name) e NAO e renomeado. CEP fica so interno (nunca em arte publica).

BEGIN;

DO $$ BEGIN
  CREATE TYPE store_type AS ENUM ('loja', 'filial', 'cd', 'online');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE stores
  ADD COLUMN IF NOT EXISTS store_type     store_type,
  ADD COLUMN IF NOT EXISTS store_code     text,          -- filial / loja / CD do varejista
  ADD COLUMN IF NOT EXISTS neighborhood   text,          -- bairro (exibicao)
  ADD COLUMN IF NOT EXISTS address_line   text,          -- logradouro + numero (interno)
  ADD COLUMN IF NOT EXISTS postal_code    varchar(9),    -- interno; nunca em arte publica
  ADD COLUMN IF NOT EXISTS latitude       numeric(9,6),
  ADD COLUMN IF NOT EXISTS longitude      numeric(9,6),
  ADD COLUMN IF NOT EXISTS region_bucket  text,          -- 'campinas' | 'fora' | 'online'
  ADD COLUMN IF NOT EXISTS display_label  text,          -- rotulo curado opcional (ex. 'Dunlop 24h')
  ADD COLUMN IF NOT EXISTS field_sources  jsonb NOT NULL DEFAULT '{}'::jsonb,
      -- proveniencia por campo: {"neighborhood":"atacadao-app|viacep|manual", ...}
  ADD COLUMN IF NOT EXISTS curated_at     timestamptz;   -- campo manual vence a fonte

ALTER TABLE stores
  ADD CONSTRAINT ck_stores_region_bucket
    CHECK (region_bucket IS NULL OR region_bucket IN ('campinas', 'fora', 'online'));

CREATE INDEX IF NOT EXISTS ix_stores_filters
  ON stores (region_bucket, city, neighborhood, store_type) WHERE active;

-- Nome de exibicao calculado (view: o nome da rede vem de retailers).
CREATE OR REPLACE VIEW store_display AS
SELECT s.id,
       r.slug                                   AS retailer_slug,
       r.name                                   AS rede,
       s.city                                   AS cidade,
       s.neighborhood                           AS bairro,
       s.store_type                             AS tipo,
       s.store_code,
       s.region_bucket,
       s.active,
       concat_ws(' - ',
         r.name,
         CASE WHEN s.store_type = 'online' THEN NULL ELSE s.city END,
         CASE s.store_type WHEN 'loja' THEN 'Loja' WHEN 'filial' THEN 'Filial'
                           WHEN 'cd' THEN 'CD' WHEN 'online' THEN 'Online' END,
         s.neighborhood)                        AS display_name,
       -- rotulo curto (mobile): "Atacadao Hortolandia" ou "Atacadao Hortolandia (P. Sao Miguel)"
       concat(r.name, ' ', coalesce(s.display_label, s.city),
              CASE WHEN count(*) OVER (PARTITION BY s.retailer_id, s.city) > 1
                   THEN ' (' || coalesce(s.neighborhood, s.store_code) || ')' END) AS short_label
FROM stores s JOIN retailers r ON r.id = s.retailer_id;

-- ---------------------------------------------------------------- backfill
-- 1) Regras deterministicas
UPDATE stores SET store_type = 'online', region_bucket = 'online',
       field_sources = field_sources || '{"store_type":"rule"}'
 WHERE city = 'Nacional';
UPDATE stores SET store_type = 'loja', field_sources = field_sources || '{"store_type":"rule"}'
 WHERE store_type IS NULL;
UPDATE stores SET region_bucket = CASE WHEN city IN (
   'Campinas','Hortolândia','Sumaré','Americana','Indaiatuba','Itu','Jundiaí',
   'Santa Bárbara d''Oeste','Monte Mor','Valinhos','Vinhedo','Paulínia','Nova Odessa')
   THEN 'campinas' ELSE 'fora' END
 WHERE region_bucket IS NULL;          -- Vila Maria (Sao Paulo) => 'fora'

-- 2) Atacadao: dados do endpoint de lojas do app (busca-loja-via-cidade-nome/v2:
--    neighborhood, zipCode, latitude, longitude, address, number) -> job de backfill
--    em Python (scripts/backfill_store_metadata.py, a escrever), nao SQL fixo.
-- 3) Demais: ViaCEP pelo CEP REAL da loja (nunca pelo CEP de referencia 13184-222).
-- 4) Curadoria manual (ver docs/stores/store-enrichment-proposal.md, secao Gaps).
-- Exemplo de override manual:
-- UPDATE stores SET neighborhood='Remanso Campineiro', curated_at=now(),
--        field_sources = field_sources || '{"neighborhood":"manual"}'
--  WHERE name='Atacadão Hortolândia';

COMMIT;
