"""Batch backfill of ``normalized_product_versions`` with the canonical normalizer.

Reads the CURRENT version of every active source product (read-only), normalizes the
whole corpus in memory (the coverage group needs cross-retailer matches), and INSERTs
rows into ``normalized_product_versions`` under ``NORMALIZER_VERSION``. Idempotent
(``ON CONFLICT DO NOTHING`` on the UNIQUE (version, normalizer_version, pipeline_version)).
No other table is touched.
"""

from __future__ import annotations

import collections
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.canonical.normalize import (
    ALL_RULES,
    GROUPS,
    NORMALIZER_VERSION,
    PIPELINE_VERSION,
    Normalized,
    SourceRow,
    gtin_checksum_ok,
    identity_fingerprint,
    normalize_corpus,
    size_columns,
)
from app.db.models_v2 import NormalizedProductVersion

PROTOTYPE_V3 = {"A1": 121420, "A2": 79882, "B1": 13417, "B2": 304, "B3": 7858, "B4": 3862, "C": 255, "R": 1021}
PROTOTYPE_N = 228019

CURRENT_ROWS_SQL = text(
    """
    SELECT spv.id, r.slug, spv.raw_name, coalesce(spv.raw_brand, ''),
           coalesce(spv.raw_gtin, ''), spv.raw_categories
      FROM source_products sp
      JOIN source_product_versions spv ON spv.id = sp.current_version_id
      JOIN catalog_sources cs ON cs.id = sp.source_id
      JOIN retailers r ON r.id = cs.retailer_id
     WHERE sp.active
     ORDER BY spv.id
    """
)


def load_current_rows(db: Session) -> list[SourceRow]:
    rows = []
    for spv_id, slug, name, brand, gtin, cats in db.execute(CURRENT_ROWS_SQL):
        rows.append(SourceRow(spv_id, slug, name or "", brand, gtin, tuple(c for c in (cats or []) if isinstance(c, str))))
    return rows


def to_record(x: Normalized) -> dict:
    p = x.parsed
    value, unit, label = size_columns(p)
    flags = list(x.flags)
    if not p.size:
        flags.append("no_size")
    if p.conflict:
        flags.append("size_conflict")
    if p.multi:
        flags.append("multi_size")
    return dict(
        source_product_version_id=x.id,
        normalizer_version=NORMALIZER_VERSION,
        pipeline_version=PIPELINE_VERSION,
        normalized_name=x.canonical_name or x.title,
        normalized_brand=x.brand_name if x.brand_origin in ("source", "inferred") else None,
        validated_gtin=x.gtin if x.gtin and gtin_checksum_ok(x.gtin) else None,
        quantity=value,
        unit=unit,
        package_type=p.pkg or None,
        identity_fingerprint=identity_fingerprint(x),
        attributes={"title": x.title, "size_src": p.size_src, "rules": "v3+c1-c7"},
        quality_flags=flags,
        coverage_group=x.group,
        department=x.department,
        brand_key=x.brand_key or None,
        brand_origin=x.brand_origin,
        packaging=p.pkg or None,
        size_kind=p.size_src or None,
        size_value=value,
        size_unit=unit,
        size_label=label,
        pack_qty=p.pack_qty or None,
        unit_count=p.unit_count or None,
        unit_type=p.unit_type or None,
        core_key=x.core or None,
        match_key=x.key,
        canonical_name_no_brand=x.canonical_name_no_brand,
        gtin_match=x.gtin_match,
        key_match=x.key_match,
    )


def batches(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i: i + size]


def count_groups(items: list[Normalized]) -> dict[str, int]:
    c = collections.Counter(x.group for x in items)
    return {g: c.get(g, 0) for g in GROUPS}


def run_backfill(db: Session, *, dry_run: bool = False, limit: int | None = None, batch_size: int = 2000, log=print) -> dict:
    rows = load_current_rows(db)
    log(f"loaded {len(rows)} current source_product_versions")
    items = normalize_corpus(rows, ALL_RULES)
    groups = count_groups(items)
    log(f"normalized corpus: {groups}")
    todo = items[:limit] if limit else items
    inserted = 0
    if not dry_run:
        for chunk in batches(todo, batch_size):
            stmt = insert(NormalizedProductVersion).values([to_record(x) for x in chunk])
            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_normalized_versions_source_pipeline"
            ).returning(NormalizedProductVersion.id)
            inserted += len(db.execute(stmt).all())
            db.commit()
            log(f"  batch committed: {inserted} inserted / {len(todo)}")
    return {"total": len(items), "selected": len(todo), "inserted": inserted, "dry_run": dry_run,
            "corpus_groups": groups, "items": items}


def db_group_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        text("SELECT coverage_group, count(*) FROM normalized_product_versions "
             "WHERE normalizer_version = :v AND pipeline_version = :p GROUP BY 1"),
        {"v": NORMALIZER_VERSION, "p": PIPELINE_VERSION},
    ).all()
    d = dict(rows)
    return {g: int(d.get(g, 0)) for g in GROUPS}


def render_report(counts: dict[str, int], items: list[Normalized] | None = None) -> str:
    n = sum(counts.values())
    a = counts["A1"] + counts["A2"]
    lines = [
        "# Backfill canônico — relatório de cobertura",
        "",
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} (America/Sao_Paulo). "
        f"normalizer_version `{NORMALIZER_VERSION}`, pipeline_version `{PIPELINE_VERSION}`.",
        "",
        f"Base: {n:,} versões atuais de produtos ativos (protótipo: {PROTOTYPE_N:,}).",
        "",
        "| Grupo | Backfill | % | Protótipo v3 | % | Δ |",
        "|---|---|---|---|---|---|",
    ]
    pn = sum(PROTOTYPE_V3.values())
    for g in GROUPS:
        lines.append(f"| {g} | {counts[g]:,} | {100 * counts[g] / n:.1f}% | {PROTOTYPE_V3[g]:,} | {100 * PROTOTYPE_V3[g] / pn:.1f}% | {counts[g] - PROTOTYPE_V3[g]:+,} |")
    pa = PROTOTYPE_V3["A1"] + PROTOTYPE_V3["A2"]
    lines.append(f"| **A1+A2** | {a:,} | {100 * a / n:.1f}% | {pa:,} | {100 * pa / pn:.1f}% | {a - pa:+,} |")
    if items:
        fl = collections.Counter(f for x in items for f in x.flags)
        lines += ["", "## Flags de qualidade", ""] + [f"- `{k}`: {v:,}" for k, v in fl.most_common()]
        by = collections.defaultdict(collections.Counter)
        for x in items:
            by[x.retailer][x.group] += 1
        lines += ["", "## Por rede (A1+A2 %)", "", "| rede | N | A1+A2 |", "|---|---|---|"]
        for r, c in sorted(by.items(), key=lambda t: -sum(t[1].values())):
            t = sum(c.values())
            lines.append(f"| {r} | {t:,} | {100 * (c['A1'] + c['A2']) / t:.1f}% |")
    return "\n".join(lines) + "\n"


def write_report(path: Path, text_: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_, encoding="utf-8")
