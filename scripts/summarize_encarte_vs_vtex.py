"""Summarise the encarte vs VTEX report by match confidence."""
from __future__ import annotations

import re
from pathlib import Path

REPORT = Path(r"C:\Android\capture\encarte_vs_vtex.md")
ROW = re.compile(r"^\| (?P<product>.+?) \| (?P<varejo>[^|]+?) \| (?P<app>[^|]+?) \| (?P<cartao>[^|]+?) \| "
                 r"(?P<cat>[^|]+?) \| (?P<sim>[^|]+?) \| (?P<simcep>[^|]+?) \| (?P<verdict>[^|]+?) \|$")


def main() -> None:
    rows = []
    for line in REPORT.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line.strip())
        if not match:
            continue
        verdict = match.group("verdict").strip()
        ratio = float(re.search(r"\(([\d.]+)\)", verdict).group(1)) if "(" in verdict else 0.0
        rows.append({**match.groupdict(), "verdict": verdict.split(" (")[0], "ratio": ratio})

    for threshold in (0.85, 0.72, 0.0):
        subset = [r for r in rows if r["ratio"] >= threshold]
        same = [r for r in subset if r["verdict"] == "= varejo"]
        print(f"ratio >= {threshold:<4} n={len(subset):>3}  varejo==VTEX: {len(same):>3} "
              f"({100 * len(same) / max(1, len(subset)):.0f}%)")

    print("\n--- nao coincidentes com ratio >= 0.85 ---")
    for row in rows:
        if row["ratio"] >= 0.85 and row["verdict"] != "= varejo":
            print(f"  {row['product'][:58]:<60} encarte {row['varejo']:>7} | VTEX {row['sim']:>7} "
                  f"| {row['verdict']} ({row['ratio']})")
            print(f"      match VTEX: {row['verdict']}")


if __name__ == "__main__":
    main()
