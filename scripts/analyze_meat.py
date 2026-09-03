"""Coverage analysis for the Açougue parser over exported names.

Usage: python scripts/analyze_meat.py <names.csv>
The CSV must have columns: source_slug, name (no header).
"""

from __future__ import annotations

import collections
import csv
import io
import sys

from app.enrichment.meat import parse_meat
from app.enrichment.resolver import MeatItem, group_comparable


def _read_csv(path: str) -> str:
    with open(path, "rb") as stream:
        raw = stream.read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def main(path: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows: list[tuple[str, str]] = []
    for source, name in csv.reader(io.StringIO(_read_csv(path))):
        rows.append((source, name))

    items = [MeatItem(retailer=source, store=None, product_id=0, raw_name=name) for source, name in rows]

    matched = [item for item in items if item.parsed.is_meat]
    unmatched = [item for item in items if not item.parsed.is_meat]
    total = len(items)

    print(f"total={total} matched={len(matched)} "
          f"({len(matched) / total * 100:.1f}%) unmatched={len(unmatched)} "
          f"({len(unmatched) / total * 100:.1f}%)")

    print("\n-- coverage per source --")
    per_source = collections.defaultdict(lambda: [0, 0])
    for item in items:
        per_source[item.retailer][0] += 1
        if item.parsed.is_meat:
            per_source[item.retailer][1] += 1
    for source, (tot, ok) in sorted(per_source.items()):
        print(f"  {source:16s} {ok:5d}/{tot:5d} ({ok / tot * 100:5.1f}%)")

    print("\n-- species distribution --")
    for species, count in collections.Counter(i.parsed.species for i in matched).most_common():
        print(f"  {species}: {count}")

    print("\n-- top cuts --")
    for cut, count in collections.Counter(i.parsed.cut for i in matched).most_common(40):
        print(f"  {cut}: {count}")

    print("\n-- unmatched samples (first 60) --")
    for item in unmatched[:60]:
        print(f"  [{item.retailer}] {item.raw_name}")

    groups = group_comparable([i for i in matched if i.price_kg is None])
    multi = [g for g in groups if len(g["sources"]) >= 2]
    print(f"\n-- variant groups: {len(groups)} total, {len(multi)} with >=2 sources --")
    for group in multi[:40]:
        sources = ", ".join(sorted(group["sources"]))
        print(f"  {group['label']:40s} -> {sources}")


if __name__ == "__main__":
    main(sys.argv[1])
