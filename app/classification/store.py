"""Persist DeepSeek classification verdicts into ``llm_classifications``.

One row per (source_product_id, line_key); running a line again updates the
previous verdict (upsert) instead of duplicating.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models_v2 import LlmClassification


def upsert_decisions(
    db: Session,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Insert or update classification rows. Returns counts for reporting."""
    created = updated = 0
    for row in rows:
        product_id = int(row["source_product_id"])
        line_key = row["line_key"]
        existing = db.scalar(
            select(LlmClassification).where(
                LlmClassification.source_product_id == product_id,
                LlmClassification.line_key == line_key,
            )
        )
        if existing is None:
            db.add(
                LlmClassification(
                    source_product_id=product_id,
                    line_key=line_key,
                    retailer_slug=row.get("retailer_slug"),
                    decision=row["decision"],
                    reason=row.get("reason"),
                    model=row["model"],
                    batch_id=(
                        UUID(row["batch_id"]) if row.get("batch_id") else None
                    ),
                    prompt_version=row.get("prompt_version", "1"),
                )
            )
            created += 1
        else:
            existing.decision = row["decision"]
            existing.reason = row.get("reason")
            existing.model = row["model"]
            existing.retailer_slug = row.get("retailer_slug") or existing.retailer_slug
            updated += 1
    db.commit()
    return {"created": created, "updated": updated}
