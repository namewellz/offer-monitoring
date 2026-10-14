"""Extract the Keycloak token request/credentials from the mitmproxy capture."""
import json
import os
from urllib.parse import parse_qs

LOG = r"C:\Android\capture\flows.jsonl"

if not os.path.exists(LOG):
    print("no capture file yet:", LOG)
    raise SystemExit(1)

entries = []
with open(LOG, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            pass

print(f"total flow entries: {len(entries)}")

# hosts seen
hosts = {}
for e in entries:
    if e.get("type") == "request":
        h = e.get("host", "")
        hosts[h] = hosts.get(h, 0) + 1
print("\nhosts:")
for h, c in sorted(hosts.items(), key=lambda x: -x[1]):
    print(f"  {c:5d}  {h}")

# look for token/auth requests
print("\n=== auth / token requests ===")
for e in entries:
    if e.get("type") != "request":
        continue
    url = e.get("url", "")
    body = e.get("body") or ""
    if any(k in url.lower() for k in ("token", "oauth", "auth", "infosec")) or "client_secret" in body or "grant_type" in body:
        print("URL:", url)
        print("  headers:", json.dumps(e.get("headers", {}), ensure_ascii=False)[:600])
        print("  body:", body[:600])
        if "client_secret" in body:
            try:
                print("  PARSED:", parse_qs(body))
            except Exception:
                pass
        print()

# also dump any request to freyr
print("\n=== freyr requests (first 30) ===")
n = 0
for e in entries:
    if e.get("type") == "request" and "freyr" in e.get("host", ""):
        print(e.get("method"), e.get("url"))
        hdrs = e.get("headers", {})
        auth = hdrs.get("Authorization") or hdrs.get("authorization")
        if auth:
            print("   Authorization:", auth[:120])
        if e.get("body"):
            print("   body:", str(e["body"])[:300])
        n += 1
        if n >= 30:
            break
