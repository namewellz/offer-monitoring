"""Export a review markdown of Açougue classifications.

For every meat family (variant group) it lists every member item from each
source, so false positives (different products wrongly grouped) are easy to
spot. Each item row has an "Observações" column left blank for human review.

Usage:
    docker compose exec api python -m scripts.export_butcher_review --out /data/acougue_review.md
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.catalog.v2.read import current_listings
from app.db.session import SessionLocal
from app.enrichment.meat import ParsedMeat
from app.enrichment.resolver import MeatItem

_IDX = {"effective_cents": 2, "product_id": 7, "raw_name": 9, "retailer": 14, "store": 15}


def _brl(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _attr_label(parsed: ParsedMeat) -> str:
    parts = []
    if parsed.bone_state == "sem_osso":
        parts.append("sem osso")
    elif parsed.bone_state == "com_osso":
        parts.append("com osso")
    if parsed.skin_state == "com_pele":
        parts.append("com pele")
    elif parsed.skin_state == "sem_pele":
        parts.append("sem pele")
    if parsed.presentation:
        parts.append(parsed.presentation)
    if parsed.conservation:
        parts.append(parsed.conservation)
    if parsed.seasoned:
        parts.append("temperado")
    return ", ".join(parts) if parts else "sem atributos adicionais"


def _collect(db: Session) -> list[MeatItem]:
    items: list[MeatItem] = []
    for row in current_listings(db):
        raw_name = row[_IDX["raw_name"]]
        effective = row[_IDX["effective_cents"]]
        if effective is None or effective <= 0:
            continue
        item = MeatItem(
            retailer=row[_IDX["retailer"]],
            store=row[_IDX["store"]],
            product_id=row[_IDX["product_id"]],
            raw_name=raw_name,
            effective_price_cents=effective,
        )
        if item.parsed.is_meat:
            items.append(item)
    return items


def _ordered_groups(items: list[MeatItem]) -> list[tuple[tuple[Any, ...], list[MeatItem]]]:
    groups: dict[tuple[Any, ...], list[MeatItem]] = defaultdict(list)
    for item in items:
        key = item.parsed.variant_key
        if key is not None:
            groups[key].append(item)
    return sorted(groups.items(), key=lambda kv: -len(kv[1]))


def build_json(items: list[MeatItem]) -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    for index, (_key, members) in enumerate(_ordered_groups(items), start=1):
        first = members[0].parsed
        prices = [m.price_kg for m in members if m.price_kg is not None]
        sources = sorted({m.retailer for m in members})
        families.append(
            {
                "id": index,
                "label": first.label,
                "species": first.species,
                "cut": first.cut,
                "bone_state": first.bone_state,
                "skin_state": first.skin_state,
                "presentation": first.presentation,
                "conservation": first.conservation,
                "seasoned": first.seasoned,
                "sale_mode": first.sale_mode,
                "item_count": len(members),
                "sources": sources,
                "price_kg_min": float(min(prices)) if prices else None,
                "price_kg_max": float(max(prices)) if prices else None,
                "observations": "",
                "items": [
                    {
                        "source": m.retailer,
                        "store": m.store,
                        "price_kg": float(m.price_kg) if m.price_kg is not None else None,
                        "raw_name": m.raw_name,
                        "product_id": m.product_id,
                        "observations": "",
                    }
                    for m in members
                ],
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_items": len(items),
        "total_families": len(families),
        "families_with_associations": sum(1 for f in families if f["item_count"] >= 2),
        "families": families,
    }


def build_markdown(items: list[MeatItem]) -> str:
    ordered = _ordered_groups(items)

    out: list[str] = []
    out.append("# Revisão de classificação — Açougue (motor determinístico)")
    out.append("")
    out.append(f"Gerado em {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}.")
    out.append("")
    out.append(
        "Cada seção é uma **família** (corte agrupado por espécie/corte/osso/pele/"
        "apresentação/conservação/tempero). As linhas são os itens reais de cada "
        "fonte associados à família. Preencha a coluna **Observações** com suas "
        "ponderações — principalmente quando dois produtos **diferentes** foram "
        "agrupados (falso positivo)."
    )
    out.append("")

    multi = [(k, v) for k, v in ordered if len(v) >= 2]
    single = [(k, v) for k, v in ordered if len(v) == 1]

    if not multi and not single:
        out.append("Nenhuma família encontrada.")
        return "\n".join(out)

    def render_family(index: int, key: tuple[Any, ...], members: list[MeatItem]) -> None:
        first = members[0].parsed
        sources = sorted({m.retailer for m in members})
        prices = [m.price_kg for m in members if m.price_kg is not None]
        cheapest = min(prices) if prices else None
        out.append(f"## {index}. {first.label}")
        out.append("")
        out.append(
            f"- **atributos**: {_attr_label(first)}"
        )
        out.append(
            f"- **{len(members)} item(ns) · {len(sources)} fonte(s)**: "
            f"{', '.join(sources)}"
        )
        if cheapest is not None:
            out.append(f"- **preço/kg**: de {_brl(cheapest)} até {_brl(max(prices))}")
        out.append("")
        out.append("| # | Fonte | R$/kg | Nome original | Observações |")
        out.append("|---|-------|-------|---------------|-------------|")
        for row_number, member in enumerate(members, start=1):
            out.append(
                f"| {row_number} | {member.retailer} | {_brl(member.price_kg)} | "
                f"{member.raw_name} |  |"
            )
        out.append("")

    number = 0
    for key, members in multi:
        number += 1
        render_family(number, key, members)
    out.append("---")
    out.append("")
    out.append(f"Famílias com apenas 1 item (sem associação entre fontes): **{len(single)}**.")
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="output file path (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        help="output format (default: inferred from --out extension, else md)",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        items = _collect(db)
    fmt = args.format or ("json" if args.out and args.out.lower().endswith(".json") else "md")
    if fmt == "json":
        import json

        payload = build_json(items)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        content = build_markdown(items)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as stream:
            stream.write(content)
        print(f"written: {args.out} ({fmt})", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(content)


if __name__ == "__main__":
    main()
