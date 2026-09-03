"""Draw up to N distinct items per Açougue family for review sampling.

Reads the review JSON (outputs/acougue_review.json) and writes a smaller sample
file: for each family, up to ``--count`` distinct raw names chosen to spread
across sources.

Usage:
    python scripts/sample_butcher.py --in outputs/acougue_review.json \
        --out outputs/acougue_sample.json --count 4
"""

from __future__ import annotations

import argparse
import json
import random


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="source", default="outputs/acougue_review.json")
    parser.add_argument("--out", dest="target", default="outputs/acougue_sample.json")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with open(args.source, encoding="utf-8") as stream:
        data = json.load(stream)

    rng = random.Random(args.seed)
    sample_families = []
    total_items = 0
    for family in data["families"]:
        # Distinct by raw_name first, then spread across sources.
        seen: dict[str, list] = {}
        for item in family["items"]:
            seen.setdefault(item["raw_name"].casefold(), item)
        distinct = list(seen.values())
        if len(distinct) <= args.count:
            chosen = distinct
        else:
            # keep family observations; pick a mix
            chosen = rng.sample(distinct, args.count)
        chosen.sort(key=lambda it: (it["source"], it["raw_name"]))
        family["items"] = chosen
        family["item_count"] = len(chosen)
        total_items += len(chosen)
        sample_families.append(family)

    out = {
        "generated_at": data["generated_at"],
        "sampled_items_per_family": args.count,
        "total_items": total_items,
        "total_families": len(sample_families),
        "families": sample_families,
    }
    with open(args.target, "w", encoding="utf-8") as stream:
        json.dump(out, stream, ensure_ascii=False, indent=2)
    print(f"written: {args.target} ({total_items} items / {len(sample_families)} families)")


if __name__ == "__main__":
    main()
