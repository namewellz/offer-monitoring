"""Drive the BlueStacks app UI through uiautomator.

  python scripts/ui_taps.py dump                 # lista textos + centros
  python scripts/ui_taps.py tap "Próximo"        # toca no elemento com esse texto
  python scripts/ui_taps.py tapxy 450 1535
  python scripts/ui_taps.py screen               # tira screenshot
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
DEVICE = "127.0.0.1:5555"
XML = Path(r"C:\Android\capture\ui.xml")
SHOT = Path(r"C:\Android\capture\screen.png")
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def adb(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(
        [ADB, "-s", DEVICE, *args], capture_output=True, text=True, timeout=timeout, errors="replace"
    )
    return (result.stdout or "") + (result.stderr or "")


def ensure_connected() -> None:
    if DEVICE not in adb("devices"):
        adb("connect", DEVICE)
        time.sleep(3)


def dump() -> list[dict]:
    ensure_connected()
    adb("shell", "rm", "-f", "/sdcard/ui.xml")
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    adb("pull", "/sdcard/ui.xml", str(XML))
    if not XML.exists():
        return []
    try:
        tree = ET.parse(XML)
    except ET.ParseError:
        return []
    nodes: list[dict] = []
    for node in tree.iter("node"):
        text = (node.get("text") or "").strip()
        desc = (node.get("content-desc") or "").strip()
        match = BOUNDS.match(node.get("bounds") or "")
        if not match:
            continue
        x0, y0, x1, y1 = map(int, match.groups())
        nodes.append(
            {
                "text": text or desc,
                "label": text or desc,
                "center": ((x0 + x1) // 2, (y0 + y1) // 2),
                "bounds": (x0, y0, x1, y1),
                "clickable": node.get("clickable") == "true",
                "resource_id": node.get("resource-id") or "",
                "class": node.get("class") or "",
            }
        )
    return nodes


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "dump"

    if action == "dump":
        nodes = dump()
        print(f"{len(nodes)} nodes")
        for node in nodes:
            if node["label"]:
                print(f"  {node['label'][:60]:<62} center={node['center']} clickable={node['clickable']}")
        return

    if action == "tap":
        target = sys.argv[2]
        nodes = dump()
        exact = [n for n in nodes if n["label"] == target]
        partial = [n for n in nodes if target.lower() in n["label"].lower()]
        candidates = exact or partial
        if not candidates:
            print(f"nao achei '{target}'. Textos disponiveis:")
            for node in nodes:
                if node["label"]:
                    print(f"   {node['label'][:60]}")
            return
        node = candidates[0]
        print(f"tap {node['label'][:50]!r} em {node['center']}")
        ensure_connected()
        print(adb("shell", f"input tap {node['center'][0]} {node['center'][1]}"))
        return

    if action == "tapxy":
        ensure_connected()
        print(adb("shell", f"input tap {sys.argv[2]} {sys.argv[3]}"))
        return

    if action == "screen":
        ensure_connected()
        adb("shell", "screencap -p /sdcard/screen.png")
        adb("pull", "/sdcard/screen.png", str(SHOT))
        print(f"screenshot: {SHOT}")
        return

    if action == "swipe":
        ensure_connected()
        print(adb("shell", f"input swipe {sys.argv[2]} {sys.argv[3]} {sys.argv[4]} {sys.argv[5]} {sys.argv[6]}"))
        return

    print(__doc__)


if __name__ == "__main__":
    main()
