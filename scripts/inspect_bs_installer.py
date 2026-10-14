"""Inspect the BlueStacks micro installer for silent-install flags."""
from __future__ import annotations

import re
from pathlib import Path

BIN = Path(r"C:\Android\bs\BlueStacksMicroInstaller.exe")
PATTERNS = [
    b"Nullsoft", b"NSIS", b"Inno Setup", b"7-Zip", b"silent", b"/S", b"-s ",
    b"enable_root_access", b"bluestacks.conf", b"HD-Player", b"MultiInstance",
    b"INSTALLDIR", b"/D=", b"--quiet", b"--silent", b"/quiet", b"/install",
]


def main() -> None:
    blob = BIN.read_bytes()
    print(f"{len(blob)} bytes, mz={blob[:2]!r}")
    for pattern in PATTERNS:
        count = len(re.findall(re.escape(pattern), blob, re.I))
        if count:
            print(f"  {pattern.decode('latin-1'):<22} {count}")
    # printable strings that look like command-line switches
    switches = sorted({m.group(0).decode("latin-1") for m in re.findall(rb"(?<![A-Za-z0-9])--?[A-Za-z][A-Za-z0-9_-]{1,18}", blob)})
    interesting = [s for s in switches if any(k in s.lower() for k in ("sil", "quiet", "instal", "path", "nore", "force", "s "))]
    print("switches candidatos:", interesting[:40])


if __name__ == "__main__":
    main()
