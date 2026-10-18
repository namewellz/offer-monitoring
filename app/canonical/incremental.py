"""Normalize only the source versions a collection just created or changed.

A new ``source_product_versions`` row is opened when the product hash changes.
That hash is the title, brand, GTIN, categories and measure. Price lives in
``price_periods`` and the image is left out of the hash, so neither one creates
a version and neither one is normalized again.

Coverage groups need the whole active catalog (a GTIN match is cross-retailer),
so the corpus is normalized in memory. Only versions of this retailer that do
not yet have a row for the current normalizer version are inserted. Bumping
``NORMALIZER_VERSION`` is what makes the next run redo a retailer.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.canonical.backfill import batches, load_current_rows, to_record
from app.canonical.normalize import (
    NORMALIZER_VERSION,
    PIPELINE_VERSION,
    Normalized,
    normalize_corpus,
)
from app.db.models_v2 import NormalizedProductVersion

PENDING_SQL = text(
    """
    SELECT spv.id
      FROM source_products sp
      JOIN source_product_versions spv ON spv.id = sp.current_version_id
      JOIN catalog_sources cs ON cs.id = sp.source_id
      JOIN retailers r ON r.id = cs.retailer_id
     WHERE sp.active
       AND r.slug = :slug
       AND NOT EXISTS (
            SELECT 1 FROM normalized_product_versions n
             WHERE n.source_product_version_id = spv.id
               AND n.normalizer_version = :v
               AND n.pipeline_version = :p
       )
    """
)


def rows_to_insert(items: list[Normalized], pending_ids: set[int]) -> list[Normalized]:
    """Keep the versions this run is allowed to write."""
    return [item for item in items if item.id in pending_ids]


def pending_version_ids(db: Session, retailer_slug: str) -> set[int]:
    rows = db.execute(
        PENDING_SQL,
        {"slug": retailer_slug, "v": NORMALIZER_VERSION, "p": PIPELINE_VERSION},
    )
    return {int(row[0]) for row in rows}


def normalize_retailer(
    db: Session,
    retailer_slug: str,
    *,
    dry_run: bool = False,
    batch_size: int = 2000,
    log=print,
) -> dict:
    pending = pending_version_ids(db, retailer_slug)
    if not pending:
        return {
            "retailer": retailer_slug,
            "pending": 0,
            "inserted": 0,
            "dry_run": dry_run,
            "normalizer_version": NORMALIZER_VERSION,
        }
    items = normalize_corpus(load_current_rows(db))
    todo = rows_to_insert(items, pending)
    inserted = 0
    if not dry_run:
        for chunk in batches(todo, batch_size):
            stmt = insert(NormalizedProductVersion).values([to_record(item) for item in chunk])
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_normalized_versions_source_pipeline"
            ).returning(NormalizedProductVersion.id)
            inserted += len(db.execute(stmt).all())
            db.commit()
            log(f"normalize {retailer_slug}: {inserted} inserted / {len(todo)}")
    return {
        "retailer": retailer_slug,
        "pending": len(pending),
        "selected": len(todo),
        "inserted": inserted,
        "dry_run": dry_run,
        "normalizer_version": NORMALIZER_VERSION,
    }
