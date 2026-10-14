-- Auditoria somente leitura. Datas TIMESTAMPTZ em UTC.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '120s';
WITH h AS (
 SELECT v.*, lag(raw_name) OVER w old_name, lag(raw_gtin) OVER w old_gtin,
 lag(id) OVER w old_id
 FROM public.source_product_versions v
 WINDOW w AS (PARTITION BY source_product_id ORDER BY version,id)
), summary AS (
 SELECT s.code, count(DISTINCT p.id) products,
 count(DISTINCT p.id) FILTER(WHERE h.old_id IS NOT NULL) with_history,
 count(h.id) versions,
 count(*) FILTER(WHERE h.old_id IS NOT NULL) transitions,
 count(*) FILTER(WHERE h.old_id IS NOT NULL AND h.raw_name IS DISTINCT FROM h.old_name) name_changes,
 count(DISTINCT p.id) FILTER(WHERE h.old_id IS NOT NULL AND h.raw_name IS DISTINCT FROM h.old_name) renamed_products,
 count(*) FILTER(WHERE h.old_id IS NOT NULL AND h.raw_gtin IS DISTINCT FROM h.old_gtin) gtin_changes
 FROM public.catalog_sources s LEFT JOIN public.source_products p ON p.source_id=s.id
 LEFT JOIN h ON h.source_product_id=p.id GROUP BY s.code
) SELECT json_agg(summary ORDER BY products DESC) FROM summary;

WITH h AS (
 SELECT v.*, lag(id) OVER w old_id, lag(raw_name) OVER w old_name,
 lag(raw_gtin) OVER w old_gtin, lag(raw_brand) OVER w old_brand,
 lag(raw_measure) OVER w old_measure, lag(first_run_id) OVER w old_run_id
 FROM public.source_product_versions v
 WINDOW w AS (PARTITION BY source_product_id ORDER BY version,id)
)
SELECT s.code, p.external_id, h.source_product_id, h.version,
 h.old_name, h.raw_name, h.old_gtin, h.raw_gtin, h.old_brand, h.raw_brand,
 h.old_measure, h.raw_measure, ro.trigger_type baseline_origin,
 ro.observed_at baseline_run_at, r.observed_at current_run_at,
 ro.target_id baseline_target, r.target_id current_target
FROM h JOIN public.source_products p ON p.id=h.source_product_id
JOIN public.catalog_sources s ON s.id=p.source_id
JOIN public.collection_runs r ON r.id=h.first_run_id
JOIN public.collection_runs ro ON ro.id=h.old_run_id
WHERE h.old_id IS NOT NULL AND (
 h.old_name IS DISTINCT FROM h.raw_name OR h.old_gtin IS DISTINCT FROM h.raw_gtin OR
 h.old_brand IS DISTINCT FROM h.raw_brand OR h.old_measure IS DISTINCT FROM h.raw_measure)
ORDER BY s.code,p.external_id,h.version;
COMMIT;

