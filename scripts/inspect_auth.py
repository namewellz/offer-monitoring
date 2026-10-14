import json
import re
import urllib.request

req = urllib.request.Request(
    "https://freyr.portal.atacadao.com.br/infosec/auth/v1/.well-known/openid-configuration"
)
req.add_header("User-Agent", "okhttp/4.12.0")
req.add_header("Accept", "application/json")
d = json.load(urllib.request.urlopen(req, timeout=30))
print("issuer:", d.get("issuer"))
print("grant_types_supported:", d.get("grant_types_supported"))
print("token_endpoint_auth_methods_supported:", d.get("token_endpoint_auth_methods_supported"))
print("scopes_supported:", d.get("scopes_supported"))
print()

rc = json.load(open(r"C:\Android\capture\remote_config.json", encoding="utf-8"))["entries"]
print("== RC keys mentioning secret/password/token/kcc ==")
for k, v in sorted(rc.items()):
    if any(t in k.lower() for t in ("secret", "password", "token", "kcc")):
        print(f"  {k} = {str(v)[:150]}")
print()
print("== RC values that look like long opaque secrets ==")
for k, v in sorted(rc.items()):
    s = str(v)
    if 24 <= len(s) <= 100 and re.fullmatch(r"[A-Za-z0-9_\-\.]{24,}", s) and not s.startswith("http"):
        print(f"  {k} = {s}")
