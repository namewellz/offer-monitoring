"""Print the captured in-store offers API traffic (plain text, via the reverse proxy)."""
from __future__ import annotations

import json
import pathlib
import sys

LOG = pathlib.Path(r"C:\Android\capture\token_requests.jsonl")
INTERESTING = ("token", "openid", "realms", "infosec", "auth")


def main() -> None:
    tail = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    if not LOG.exists():
        print("nada capturado ainda")
        return
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"total de requisicoes: {len(rows)}")
    for entry in rows[-tail:]:
        path = entry.get("path", "")
        flag = "  <== AUTH" if any(k in path.lower() for k in INTERESTING) else ""
        print(f"\n[{entry.get('ts')}] {entry.get('status')} {entry.get('method')} {path[:120]}{flag}")
        for key, value in sorted((entry.get("headers") or {}).items()):
            if key.lower() in ("authorization", "content-type", "user-agent"):
                print(f"    {key}: {value[:150]}")
        body = entry.get("body") or ""
        if body:
            print(f"    body: {body[:800]}")
        response = entry.get("response") or ""
        if response and (flag or len(response) < 400):
            print(f"    resp: {response[:400]}")


if __name__ == "__main__":
    main()
