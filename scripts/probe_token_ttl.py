"""Probe Keycloak token TTL / refresh behaviour for the Atacadao app client.

Usage: python scripts/probe_token_ttl.py
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = (
    "https://freyr.portal.atacadao.com.br"
    "/infosec/auth/v1/protocol/openid-connect/token"
)
CLIENT_ID = "OfertaMobile-TokenAuth"
CLIENT_SECRET = "CI4hKA5gdaXjDLm52Mz68pXOhIhiUvNA"
USERNAME = "kcc-ofertas-externo"
PASSWORD = "WUzN!r2Jrr!8BTFteoW3J"
UA = "Dart/3.10 (dart:io)"


def post(data: dict, ua: str = UA):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(TOKEN_URL, data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", ua)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if raw[:2] == b"\x1f\x8b":
            import gzip

            raw = gzip.decompress(raw)
        return exc.code, raw.decode("utf-8", "replace")[:400]


def main() -> None:
    base = {
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    for ua in (UA, "python-urllib/3", ""):
        status, data = post(base, ua)
        print(f"UA={ua!r:24} -> {status}")
        if status == 200:
            break
        print("   body:", data)

    if status != 200:
        print("auth failed, aborting")
        return

    print("expires_in        :", data.get("expires_in"))
    print("refresh_expires_in:", data.get("refresh_expires_in"))
    print("scope             :", data.get("scope"))
    print("token_type        :", data.get("token_type"))

    tok = data["access_token"]
    payload = tok.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    print("iss               :", claims.get("iss"))
    print("azp               :", claims.get("azp"))
    print("typ               :", claims.get("typ"))
    print("sub               :", claims.get("sub"))
    print("preferred_user    :", claims.get("preferred_username"))
    print("aud               :", claims.get("aud"))
    print("iat/exp/ttl       :", claims.get("iat"), claims.get("exp"),
          (claims.get("exp") or 0) - (claims.get("iat") or 0))
    print("realm_access      :", claims.get("realm_access"))
    print("resource_access   :", claims.get("resource_access"))
    print("all claims        :", sorted(claims.keys()))

    refresh = data.get("refresh_token")
    if refresh:
        status, data2 = post({
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        })
        print("refresh_token grant:", status,
              data2.get("expires_in") if isinstance(data2, dict) else data2)

    # service account / client_credentials?
    status, data3 = post({
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    print("client_credentials :", status,
          data3 if not isinstance(data3, dict) else "OK")


if __name__ == "__main__":
    main()
