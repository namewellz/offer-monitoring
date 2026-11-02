"""Backfill/rebuild do read model do catálogo (``store_listings``).

O read model é escrito pelo ingest a cada coleta. Estas rotinas existem para:

- ``backfill_departments``: calcular ``source_product_versions.department`` para
  as versões antigas (a coluna nasceu nula na migração 0018) e propagar para
  ``store_listings.department``. Usa a **regra atual** do taxonomy — a mesma que
  o ingest usa, então rodar depois de mudar a regra reclassifica tudo.
- ``rebuild_listings``: reescrever as colunas derivadas de produto, loja/rede e
  preço a partir da versão corrente e do período aberto. Idempotente.

Ambas são de execução manual (CLI ``backfill-catalog-read-model``), não rodam no
startup.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.db.models_v2 import SourceProductVersion

_PRODUCT_FIELDS_SQL = """
UPDATE store_listings sl
SET product_external_id = sp.external_id,
    product_name        = v.raw_name,
    product_brand       = v.raw_brand,
    product_gtin        = v.raw_gtin,
    product_categories  = v.raw_categories
FROM source_products sp
JOIN source_product_versions v ON v.id = sp.current_version_id
WHERE sl.source_product_id = sp.id
  AND (sl.product_name IS DISTINCT FROM v.raw_name
       OR sl.product_external_id IS DISTINCT FROM sp.external_id
       OR sl.product_brand IS DISTINCT FROM v.raw_brand
       OR sl.product_gtin IS DISTINCT FROM v.raw_gtin
       OR sl.product_categories IS DISTINCT FROM v.raw_categories)
"""

_STORE_FIELDS_SQL = """
UPDATE store_listings sl
SET retailer_name       = r.name,
    retailer_slug       = r.slug,
    store_name          = COALESCE(s.display_name, s.name),
    store_region_bucket = s.region_bucket,
    store_city          = s.city,
    store_neighborhood  = s.neighborhood,
    store_type          = s.store_type
FROM collection_targets ct
JOIN stores s ON s.id = ct.store_id
JOIN catalog_sources cs ON cs.id = ct.source_id
JOIN retailers r ON r.id = cs.retailer_id
WHERE ct.id = sl.target_id
  AND (sl.retailer_name IS DISTINCT FROM r.name
       OR sl.retailer_slug IS DISTINCT FROM r.slug
       OR sl.store_name IS DISTINCT FROM COALESCE(s.display_name, s.name)
       OR sl.store_region_bucket IS DISTINCT FROM s.region_bucket
       OR sl.store_city IS DISTINCT FROM s.city
       OR sl.store_neighborhood IS DISTINCT FROM s.neighborhood
       OR sl.store_type IS DISTINCT FROM s.store_type)
"""

# Mesma regra de shelf_previous_cents, em SQL: quando o preço atual é o de
# prateleira e o anterior era desconto, a base é a prateleira anterior.
_PRICE_FIELDS_SQL = """
UPDATE store_listings sl
SET regular_price_cents    = p.regular_price_cents,
    effective_price_cents  = p.effective_price_cents,
    best_conditional_cents = p.best_conditional_price_cents,
    price_basis_unit       = p.price_basis_unit,
    price_terms            = p.price_terms,
    last_confirmed_at      = p.last_confirmed_at,
    previous_cents         = b.baseline,
    change_amount_cents    = CASE
        WHEN b.baseline IS NOT NULL AND b.baseline > 0
        THEN p.effective_price_cents - b.baseline
    END,
    change_percent         = CASE
        WHEN b.baseline IS NOT NULL AND b.baseline > 0
        THEN round((p.effective_price_cents - b.baseline) * 100.0 / b.baseline, 2)
    END,
    is_offer               = (
        (p.regular_price_cents IS NOT NULL
         AND p.effective_price_cents < p.regular_price_cents)
        OR p.best_conditional_price_cents IS NOT NULL
        OR (CASE WHEN jsonb_typeof(p.price_terms) = 'array'
                 THEN jsonb_array_length(p.price_terms) ELSE 0 END) > 0
    ),
    offer_kind             = CASE
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
  AND (sl.effective_price_cents IS DISTINCT FROM p.effective_price_cents
       OR sl.regular_price_cents IS DISTINCT FROM p.regular_price_cents
       OR sl.last_confirmed_at IS DISTINCT FROM p.last_confirmed_at)
"""


def backfill_departments(db: Session, *, batch_size: int = 5000) -> dict[str, int]:
    """Calcula o departamento das versões ainda nulas e propaga aos listings."""
    versions = 0
    while True:
        pending = db.scalars(
            select(SourceProductVersion)
            .where(SourceProductVersion.department.is_(None))
            .limit(batch_size)
        ).all()
        if not pending:
            break
        for version in pending:
            version.department = canonical_department(
                version.raw_categories, version.raw_name
            )
        db.commit()
        versions += len(pending)
        if len(pending) < batch_size:
            break

    listings = db.execute(
        text(
            """
            UPDATE store_listings sl
            SET department = v.department
            FROM source_products sp
            JOIN source_product_versions v ON v.id = sp.current_version_id
            WHERE sl.source_product_id = sp.id
              AND sl.department IS DISTINCT FROM v.department
            """
        )
    ).rowcount
    db.commit()
    return {"versions": versions, "listings": int(listings or 0)}


def rebuild_listings(db: Session) -> dict[str, int]:
    """Reescreve as colunas derivadas de produto, loja e preço."""
    product_fields = db.execute(text(_PRODUCT_FIELDS_SQL)).rowcount
    db.commit()
    store_fields = db.execute(text(_STORE_FIELDS_SQL)).rowcount
    db.commit()
    price_fields = db.execute(text(_PRICE_FIELDS_SQL)).rowcount
    db.commit()
    return {
        "product_fields": int(product_fields or 0),
        "store_fields": int(store_fields or 0),
        "price_fields": int(price_fields or 0),
    }


def rebuild_all(db: Session) -> dict[str, int]:
    departments = backfill_departments(db)
    listings = rebuild_listings(db)
    return {**departments, **listings}
