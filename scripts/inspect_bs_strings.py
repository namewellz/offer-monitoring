"""Extract UTF-16/ASCII strings from the BlueStacks WPF installer to find CLI flags."""
from __future__ import annotations

import re
from pathlib import Path

BIN = Path(r"C:\Android\bs\BlueStacksMicroInstaller.exe")


def strings(blob: bytes, min_len: int = 4) -> set[str]:
    out: set[str] = set()
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}" % min_len, blob):  # utf-16le
        out.add(match.group(0).decode("utf-16-le", "ignore"))
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, blob):  # ascii
        out.add(match.group(0).decode("ascii", "ignore"))
    return out


def main() -> None:
    blob = BIN.read_bytes()
    found = strings(blob)
    print(f"{len(found)} strings extraidas")
    keys = ("silent", "quiet", "noreboot", "install", "argument", "commandline", "-s", "--", "/s", "path")
    hits = sorted(s for s in found if any(k in s.lower() for k in keys))
    for text in hits[:200]:
        if len(text) < 90:
            print("  ", text)


if __name__ == "__main__":
    main()
