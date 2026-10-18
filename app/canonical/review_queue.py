"""Read-only slices of the canonical review queues B1–B4 and R."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.canonical.normalize import NORMALIZER_VERSION, PIPELINE_VERSION

GROUPS = ("B1", "B2", "B3", "B4", "R")
GROUP_LABELS = {
    "B1": "Marca só inferida do título",
    "B2": "Kit ou tamanho conflitante",
    "B3": "Sem medida no título",
    "B4": "Sem marca",
    "R": "GTIN com 1 un implícita",
}

_COUNTS_SQL = text(
    """
    SELECT n.coverage_group, count(*)::int
      FROM normalized_product_versions n
      JOIN source_products sp
        ON sp.current_version_id = n.source_product_version_id
       AND sp.active
     WHERE n.normalizer_version = :v
       AND n.pipeline_version = :p
       AND n.department = :department
       AND n.coverage_group IN ('B1', 'B2', 'B3', 'B4', 'R')
     GROUP BY n.coverage_group
    """
)

_ROWS_SQL = text(
    """
    SELECT spv.raw_name, n.normalized_brand, n.size_label, n.pack_qty, r.name AS retailer
      FROM normalized_product_versions n
      JOIN source_product_versions spv ON spv.id = n.source_product_version_id
      JOIN source_products sp
        ON sp.current_version_id = spv.id
       AND sp.active
      JOIN catalog_sources cs ON cs.id = sp.source_id
      JOIN retailers r ON r.id = cs.retailer_id
     WHERE n.normalizer_version = :v
       AND n.pipeline_version = :p
       AND n.department = :department
       AND n.coverage_group = :group
     ORDER BY spv.raw_name
     LIMIT :lim
    """
)


def queue_snapshot(
    db: Session,
    department: str,
    group: str | None,
    *,
    base: str,
    limit: int = 40,
) -> dict:
    chosen = group if group in GROUPS else None
    params = {
        "v": NORMALIZER_VERSION,
        "p": PIPELINE_VERSION,
        "department": department,
    }
    counts = {code: 0 for code in GROUPS}
    for code, count in db.execute(_COUNTS_SQL, params):
        if code in counts:
            counts[code] = int(count)
    rows: list[dict] = []
    if chosen:
        fetched = db.execute(_ROWS_SQL, {**params, "group": chosen, "lim": limit}).all()
        rows = [
            {
                "name": row.raw_name or "",
                "brand": row.normalized_brand or "",
                "size": row.size_label or "",
                "pack": row.pack_qty,
                "retailer": row.retailer or "",
            }
            for row in fetched
        ]
    return {
        "department": department,
        "base": base,
        "counts": counts,
        "group": chosen,
        "label": GROUP_LABELS.get(chosen or "", ""),
        "total": counts.get(chosen, 0) if chosen else sum(counts.values()),
        "rows": rows,
    }
