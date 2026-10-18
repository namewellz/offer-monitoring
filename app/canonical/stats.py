"""Read-only canonical coverage for the home page and the update log."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.canonical.normalize import NORMALIZER_VERSION, PIPELINE_VERSION

_COVERED = frozenset({"A1", "A2"})
_REVIEW = frozenset({"B1", "B2", "B3", "B4", "R"})

_SQL = text(
    """
    SELECT r.name, n.coverage_group, count(*)::int
      FROM normalized_product_versions n
      JOIN source_product_versions spv ON spv.id = n.source_product_version_id
      JOIN source_products sp
        ON sp.current_version_id = spv.id
       AND sp.active
      JOIN catalog_sources cs ON cs.id = sp.source_id
      JOIN retailers r ON r.id = cs.retailer_id
     WHERE n.normalizer_version = :v
       AND n.pipeline_version = :p
     GROUP BY r.name, n.coverage_group
     ORDER BY r.name
    """
)


def format_pct(part: int, total: int) -> str:
    if not total:
        return "—"
    return f"{100 * part / total:.1f}".replace(".", ",") + "%"


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def coverage_snapshot(db: Session) -> dict:
    by_name: dict[str, dict[str, int]] = {}
    for name, group, count in db.execute(
        _SQL, {"v": NORMALIZER_VERSION, "p": PIPELINE_VERSION}
    ):
        bucket = by_name.setdefault(name, {})
        bucket[group or ""] = bucket.get(group or "", 0) + int(count)

    retailers = []
    total = covered = review = 0
    for name, groups in by_name.items():
        retailer_total = sum(groups.values())
        retailer_covered = sum(groups.get(group, 0) for group in _COVERED)
        retailer_review = sum(groups.get(group, 0) for group in _REVIEW)
        total += retailer_total
        covered += retailer_covered
        review += retailer_review
        retailers.append(
            {
                "name": name,
                "total": retailer_total,
                "covered": retailer_covered,
                "covered_pct": format_pct(retailer_covered, retailer_total),
                "review": retailer_review,
            }
        )
    retailers.sort(key=lambda row: (-row["total"], row["name"]))
    return {
        "total": total,
        "covered": covered,
        "covered_pct": format_pct(covered, total),
        "review": review,
        "by_retailer": retailers,
        "normalizer_version": NORMALIZER_VERSION,
    }
