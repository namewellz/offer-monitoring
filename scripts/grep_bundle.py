"""Grep a web/JS bundle with context — the workhorse for hybrid app analysis.

Minified bundles are single-line files, so `Select-String` and normal grep drown
you in noise. This tool finds every match of a pattern and prints a window of
characters around it, which is how you read the configuration block, the API
route templates and the request parameters of a Capacitor/Cordova app.

Usage
-----
    python scripts/grep_bundle.py <dir-or-file> <regex> [--context 220] [--max 5]
    python scripts/grep_bundle.py "C:\\Android\\apktool\\spani_src\\assets" televendas
    python scripts/grep_bundle.py <dir> "org/\\$\\{?org" --context 300
    python scripts/grep_bundle.py <dir> "api-admin/v1[^\"']{0,60}" --max 40
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TEXT_SUFFIXES = {".js", ".mjs", ".cjs", ".html", ".htm", ".json", ".css", ".txt", ".xml", ".smali"}


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("pattern")
    parser.add_argument("--context", type=int, default=200, help="caracteres antes/depois do match")
    parser.add_argument("--max", type=int, default=6, help="máximo de matches por arquivo")
    parser.add_argument("--files-only", action="store_true", help="mostra só os arquivos que casam")
    args = parser.parse_args()

    regex = re.compile(args.pattern, re.IGNORECASE)
    total = 0
    for path in iter_files(Path(args.root)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = list(regex.finditer(text))
        if not matches:
            continue
        if args.files_only:
            print(f"{path.name}: {len(matches)} match(es)")
            total += len(matches)
            continue
        print(f"\n########## {path.name} ({len(matches)} match(es)) ##########")
        for match in matches[: args.max]:
            start = max(0, match.start() - args.context)
            end = min(len(text), match.end() + args.context)
            print(f"\n--- @{match.start()} ---")
            print(text[start:end].replace("\n", " "))
        total += len(matches)
    print(f"\n=== {total} match(es) ===")


if __name__ == "__main__":
    main()
