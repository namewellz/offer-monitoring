"""Canonical Açougue categories.

Two concerns:
- ``CANONICAL_CATEGORIES``: the controlled vocabulary sent to the LLM so it
  answers with a fixed set of names (no more "Acém"/"Acém Bovino"/"Acém em
  Cubos" drift). Extend/curate freely.
- ``llm_category_labels``: DB overrides mapping each raw label the model already
  produced to the canonical display name. Editing it (via the "Categorias"
  screen) fixes/merges categories without re-running the model.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models_v2 import LlmCategoryLabel, LlmClassification

# Curated closed vocabulary used to steer the LLM (and shown on the screen).
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Alcatra", "Ancho", "Aranha", "Acém", "Bacon", "Bisteca Suína",
    "Bucho", "Capa de Filé", "Carne Bovina Salgada", "Carne Moída",
    "Carne Seca", "Carne Suína Salgada", "Carré Suíno", "Charque",
    "Contra-filé", "Copa Lombo", "Coração Bovina", "Coração de Frango",
    "Costela Bovina", "Costela de Cordeiro", "Costela Suína", "Coxão Duro",
    "Coxão Mole", "Cupim", "Entranha", "Figado Bovino", "Figado de Frango",
    "Filé de Frango", "Filé de Peixe", "Filé Mignon", "Fraldinha",
    "Frango a Passarinho", "Frango Caipira", "Frango Inteiro", "Lagarto",
    "Linguiça Calabresa", "Linguiça Cuiabana", "Linguiça Defumada",
    "Linguiça de Frango", "Linguiça Fininha", "Linguiça Mista",
    "Linguiça Paio", "Linguiça Pernil", "Linguiça Portuguesa",
    "Linguiça Suína", "Linguiça Toscana", "Linguiça Vegana", "Lombo Suíno",
    "Maminha", "Moela", "Músculo", "Paleta Suína", "Panceta", "Papada",
    "Patinho", "Peito de Frango", "Peito de Peru Defumado", "Peito Bovina",
    "Pernil Suíno", "Picanha", "Presunto Fatiado", "Pulmão", "Rabo Suíno",
    "Salsicha", "Sassami", "Sobrecoxa de Frango", "Asa de Frango",
    "Coxa de Frango", "Coxinha da Asa", "Bacalhau", "Camarão",
    "Filé de Peixe Branco", "Peixe Inteiro", "Salmão", "Tilápia",
)


def seed_categories(db: Session) -> int:
    """Insert distinct accepted categories (from LLM runs) as editable labels.

    New labels default canonical = label; existing entries are untouched so user
    overrides survive new classification runs.
    """
    labels = db.execute(
        select(LlmClassification.line_key)
        .where(
            LlmClassification.decision == "accept",
            LlmClassification.line_key.notin_(("reject", "NAO_CARNE")),
        )
        .distinct()
    ).scalars().all()
    existing = set(
        db.execute(select(LlmCategoryLabel.label)).scalars().all()
    )
    added = 0
    for label in labels:
        if label and label not in existing:
            db.add(LlmCategoryLabel(label=label, canonical=label))
            added += 1
    if added:
        db.commit()
    return added


def canonical_map(db: Session) -> dict[str, str]:
    """label -> canonical (defaults to label when absent)."""
    rows = db.execute(select(LlmCategoryLabel.label, LlmCategoryLabel.canonical)).all()
    return {label: canonical for label, canonical in rows}


def category_counts(db: Session) -> list[dict[str, Any]]:
    """Raw labels in use (accepted), with item count, for the edit screen."""
    rows = db.execute(
        select(
            LlmClassification.line_key.label("label"),
            func.count().label("n"),
        )
        .where(
            LlmClassification.decision == "accept",
            LlmClassification.line_key.notin_(("reject", "NAO_CARNE")),
        )
        .group_by(LlmClassification.line_key)
        .order_by(func.count().desc())
    ).all()
    overrides = canonical_map(db)
    return [
        {
            "label": label,
            "canonical": overrides.get(label, label),
            "count": n,
        }
        for label, n in rows
    ]


def set_canonicals(db: Session, updates: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert canonical for the given labels. Returns (created, updated)."""
    created = updated = 0
    for update in updates:
        label = (update.get("label") or "").strip()
        canonical = (update.get("canonical") or label).strip() or label
        if not label:
            continue
        existing = db.execute(
            select(LlmCategoryLabel).where(LlmCategoryLabel.label == label)
        ).scalar_one_or_none()
        if existing is None:
            db.add(LlmCategoryLabel(label=label, canonical=canonical))
            created += 1
        elif existing.canonical != canonical:
            existing.canonical = canonical
            updated += 1
    db.commit()
    return {"created": created, "updated": updated}
