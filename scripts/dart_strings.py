"""Dump printable strings from a Flutter `libapp.so` (Dart AOT snapshot) and grep them.

The Dart AOT snapshot keeps most of the app's contract in clear text: URLs,
route templates, config keys and (sometimes) credentials that were injected via
`--dart-define`. This tool is the cheapest first step when an app-update breaks
a collector, before any emulator/proxy work.

Usage:
    python scripts/dart_strings.py dump  <libapp.so> [--out strings.txt] [--minlen 6]
    python scripts/dart_strings.py grep  <libapp.so|strings.txt> <kw> [kw ...] [--context 3] [--max 40]

`grep` prints the line index, the matching line and `--context` neighbours, so you
can see blocks that were laid out back to back in the snapshot (typical layout of
dart-define blocks: client_id right above client_secret).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

def _printable(minlen: int) -> re.Pattern[bytes]:
    return re.compile(rb"[\x20-\x7e\t]{" + str(minlen).encode() + rb",}")


def iter_strings(blob: bytes, minlen: int = 6):
    for m in _printable(minlen).finditer(blob):
        yield m.start(), m.group().decode("ascii", "replace")


def dump(path: Path, out: Path, minlen: int) -> None:
    blob = path.read_bytes()
    n = 0
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for off, s in iter_strings(blob, minlen):
            fh.write(f"{off:#010x}\t{s}\n")
            n += 1
    print(f"{n} strings -> {out}")


def load_lines(path: Path, minlen: int) -> list[str]:
    if path.suffix == ".txt":
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [ln.split("\t", 1)[1] if "\t" in ln else ln for ln in raw]
    blob = path.read_bytes()
    return [s for _off, s in iter_strings(blob, minlen)]


def grep(path: Path, keywords: list[str], context: int, maxhits: int, minlen: int) -> int:
    lines = load_lines(path, minlen)
    total = 0
    for kw in keywords:
        hits = [i for i, ln in enumerate(lines) if kw in ln and len(ln) < 400]
        print(f"===== {kw} ({len(hits)} hits) =====")
        total += len(hits)
        seen: set[int] = set()
        for i in hits[:maxhits]:
            lo, hi = max(0, i - context), min(len(lines), i + context + 1)
            if any(j in seen for j in range(lo, hi)):
                continue
            for j in range(lo, hi):
                seen.add(j)
                mark = ">" if j == i else "."
                line = lines[j].strip()
                if len(line) > 240:
                    line = line[:240] + "…"
                print(f"  {mark} [{j}] {line}")
            print()
    return total


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump")
    d.add_argument("path", type=Path)
    d.add_argument("--out", type=Path, default=None)
    d.add_argument("--minlen", type=int, default=6)

    g = sub.add_parser("grep")
    g.add_argument("path", type=Path)
    g.add_argument("keywords", nargs="+")
    g.add_argument("--context", type=int, default=3)
    g.add_argument("--max", type=int, default=40, dest="maxhits")
    g.add_argument("--minlen", type=int, default=6)

    args = ap.parse_args(argv)
    if args.cmd == "dump":
        out = args.out or args.path.with_suffix(".strings.txt")
        dump(args.path, out, args.minlen)
        return 0
    if not args.path.exists():
        print(f"not found: {args.path}", file=sys.stderr)
        return 2
    grep(args.path, args.keywords, args.context, args.maxhits, args.minlen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
