"""Find how the 'Meu Atacadao' app detects root."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

SPLIT0 = Path.home() / "AppData/Local/Temp/atacadao-xapk/split_0.apk"
PATTERNS = [
    b"comprometem a seguran",
    b"jailbreak",
    b"JailBroken",
    b"isJailBreak",
    b"rootBeer",
    b"isRooted",
    b"checkRoot",
    b"detectRoot",
    b"superuser",
    b"magisk",
    b"test-keys",
    b"/system/xbin/su",
    b"/system/bin/su",
    b"which su",
    b"busybox",
    b"/data/local",
    b"ro.debuggable",
    b"ro.secure",
    b"frida",
    b"xposed",
    b"substrate",
    b"su_binary",
    b"flutter_jailbreak",
]


def main() -> None:
    with zipfile.ZipFile(SPLIT0) as zf:
        blob = zf.read("lib/arm64-v8a/libapp.so")

    print("=== ocorrencias ===")
    for pattern in PATTERNS:
        count = len(re.findall(re.escape(pattern), blob, re.I))
        if count:
            print(f"  {pattern.decode('latin-1'):<24} {count}")

    print("\n=== contexto do texto de bloqueio ===")
    for match in list(re.finditer(rb"comprometem a seguran", blob, re.I))[:3]:
        window = blob[max(0, match.start() - 700) : match.end() + 500]
        printable = re.findall(rb"[\x20-\x7e\xc0-\xff]{5,}", window)
        print("  " + " | ".join(s.decode("latin-1") for s in printable))
        print()

    print("=== contexto de 'jailbreak'/'root' em strings curtas ===")
    for match in list(re.finditer(rb"(jailbreak|isRooted|checkRoot|rootDetect\w*)", blob, re.I))[:6]:
        window = blob[max(0, match.start() - 250) : match.end() + 250]
        printable = re.findall(rb"[\x20-\x7e]{4,}", window)
        print("  " + " | ".join(s.decode("latin-1") for s in printable))


if __name__ == "__main__":
    main()
