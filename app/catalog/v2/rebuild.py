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

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_department
from app.catalog.v2.registry import CATALOG_SOURCES, MIN_VALID_PRICE_CENTS
from app.db.models import Retailer
from app.db.models_v2 import (
    CatalogSource,
    CollectionTarget,
    PricePeriod,
    SourceProductVersion,
    StoreListing,
)

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


def backfill_departments(db: Session, *, batch_size: int = 2000) -> dict[str, int]:
    """Calcula o departamento das versões ainda nulas e propaga aos listings.

    Pagina por ``id`` (usa a PK, não varre a tabela) e usa ``SKIP LOCKED`` para
    nunca ficar preso atrás de uma coleta em andamento, que mantém uma transação
    longa reescrevendo versões. Linhas puladas por lock ficam para a próxima
    execução — o comando é idempotente.
    """
    versions = 0
    last_id = 0
    while True:
        pending = db.scalars(
            select(SourceProductVersion)
            .where(
                SourceProductVersion.id > last_id,
                SourceProductVersion.department.is_(None),
            )
            .order_by(SourceProductVersion.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True, of=SourceProductVersion)
        ).all()
        if not pending:
            break
        last_id = pending[-1].id
        for version in pending:
            version.department = canonical_department(
                version.raw_categories, version.raw_name
            )
        db.commit()
        versions += len(pending)

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


def purge_sentinel_periods(db: Session) -> dict[str, int]:
    """Remove períodos criados a partir de preço-sentinela.

    Varejistas usam 0,01 (Max Atacadista) ou 999,9 (Assaí) quando o item está
    sem preço — tratar isso como preço real gera um período falso e uma variação
    absurda quando o preço verdadeiro volta. Aqui:

    1. apaga os períodos com preço abaixo do piso (`MIN_VALID_PRICE_CENTS`) ou
       igual ao sentinela configurado da rede;
    2. se o período apagado era o aberto, reabre o anterior (o item estava só
       indisponível, o último preço válido continua valendo);
    3. recomputa o snapshot do read model dos listings afetados.

    É idempotente e restrito: um preço real de R$ 999,90 na Pague Menos (onde
    não há sentinela configurado) não é tocado.
    """
    from app.catalog.v2.ingest import _sync_listing_snapshot

    deleted = 0
    affected: set[int] = set()
    for slug, config in CATALOG_SOURCES.items():
        conditions = [PricePeriod.effective_price_cents < MIN_VALID_PRICE_CENTS]
        if config.sentinel_cents:
            conditions.append(
                PricePeriod.effective_price_cents.in_(sorted(config.sentinel_cents))
            )
        rows = db.execute(
            select(
                PricePeriod.id,
                PricePeriod.store_listing_id,
                PricePeriod.version,
                PricePeriod.ended_at,
            )
            .join(StoreListing, StoreListing.id == PricePeriod.store_listing_id)
            .join(CollectionTarget, CollectionTarget.id == StoreListing.target_id)
            .join(CatalogSource, CatalogSource.id == CollectionTarget.source_id)
            .join(Retailer, Retailer.id == CatalogSource.retailer_id)
            .where(Retailer.slug == slug, or_(*conditions))
        ).all()
        for period_id, listing_id, version, ended_at in rows:
            db.execute(
                delete(PricePeriod).where(
                    PricePeriod.id == period_id,
                    PricePeriod.store_listing_id == listing_id,
                )
            )
            if ended_at is None:
                # O sentinela era o período aberto: o anterior volta a vigorar.
                db.execute(
                    update(PricePeriod)
                    .where(
                        PricePeriod.store_listing_id == listing_id,
                        PricePeriod.version == version - 1,
                    )
                    .values(ended_at=None)
                )
            deleted += 1
            affected.add(listing_id)
        db.commit()

    rebuilt = 0
    for listing_id in affected:
        listing = db.get(StoreListing, listing_id)
        if listing is None:
            continue
        period = db.scalar(
            select(PricePeriod).where(
                PricePeriod.store_listing_id == listing_id,
                PricePeriod.ended_at.is_(None),
            )
        )
        if period is None:
            listing.effective_price_cents = None
            listing.regular_price_cents = None
            listing.best_conditional_cents = None
            listing.price_terms = []
            listing.previous_cents = None
            listing.change_amount_cents = None
            listing.change_percent = None
            listing.is_offer = False
            listing.offer_kind = None
        else:
            previous = db.scalar(
                select(PricePeriod).where(
                    PricePeriod.store_listing_id == listing_id,
                    PricePeriod.version == period.version - 1,
                )
            )
            _sync_listing_snapshot(listing, period, previous, changed=True)
        rebuilt += 1
    db.commit()
    return {"periods_deleted": deleted, "listings_rebuilt": rebuilt}
