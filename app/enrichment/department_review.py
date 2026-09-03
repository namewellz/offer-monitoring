"""Server-rendered review screen for a classified store department.

Shows, per canonical category, how many accepted products it holds plus sample
product names per retailer (to eyeball false positives/consistency), and a
sample of the items the LLM rejected as "outside the department".
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select

from app.classification.canonical import canonical_map
from app.db.models_v2 import LlmClassification


def _retailer_label(slug: str | None) -> str:
    from app.enrichment.dashboard import RETAILER_LABELS

    return RETAILER_LABELS.get(slug or "", slug or "?")


def _product_index(db: Any) -> dict[int, dict[str, Any]]:
    """product_id -> best raw name + retailer (from the current catalog)."""
    from app.catalog.v2.read import current_listings

    index: dict[int, dict[str, Any]] = {}
    for row in current_listings(db):
        pid = row[7]
        raw = row[9] or ""
        if pid not in index or len(raw) > len(index[pid]["raw_name"]):
            index[pid] = {"raw_name": raw, "retailer": row[14]}
    return index


def department_review(
    db: Any, department: str, sample: int = 4, rejected_sample: int = 120
) -> dict[str, Any]:
    accepts = db.execute(
        select(LlmClassification).where(
            LlmClassification.department == department,
            LlmClassification.decision == "accept",
        )
    ).scalars().all()
    rejects = db.execute(
        select(LlmClassification).where(
            LlmClassification.department == department,
            LlmClassification.decision == "reject",
        )
    ).scalars().all()

    overrides = canonical_map(db, department=department)
    index = _product_index(db)

    canonical_counts: Counter = Counter()
    by_canon: dict[str, dict[str, Any]] = {}
    by_canon_labels: dict[str, Counter] = {}
    for verdict in accepts:
        label = verdict.line_key
        canonical = overrides.get(label, label)
        canonical_counts[canonical] += 1
        group = by_canon.setdefault(
            canonical, {"canonical": canonical, "count": 0, "samples": [], "labels": {}}
        )
        group["count"] += 1
        label_counts = by_canon_labels.setdefault(canonical, Counter())
        label_counts[label] += 1
        if len(group["samples"]) < sample:
            info = index.get(verdict.source_product_id, {})
            group["samples"].append(
                {
                    "retailer": _retailer_label(
                        verdict.retailer_slug or info.get("retailer")
                    ),
                    "name": info.get("raw_name") or f"produto #{verdict.source_product_id}",
                }
            )
    for canonical, group in by_canon.items():
        group["labels"] = {
            label: count
            for label, count in by_canon_labels[canonical].most_common()
        }

    rejected_rows = []
    for verdict in rejects[:rejected_sample]:
        info = index.get(verdict.source_product_id, {})
        rejected_rows.append(
            {
                "retailer": _retailer_label(
                    verdict.retailer_slug or info.get("retailer")
                ),
                "name": info.get("raw_name") or f"produto #{verdict.source_product_id}",
                "reason": verdict.reason or "",
            }
        )

    groups = sorted(by_canon.values(), key=lambda g: (-g["count"], g["canonical"]))
    return {
        "department": department,
        "accepted_products": len(accepts),
        "rejected_products": len(rejects),
        "distinct_canonicals": len(groups),
        "groups": groups,
        "rejected_rows": rejected_rows,
    }
