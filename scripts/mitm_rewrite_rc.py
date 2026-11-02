"""mitmproxy addon: rewrite the Remote Config response so the app talks to us.

The app builds its Keycloak/in-store-offers URLs from Firebase Remote Config
values (`in_store_offers_*`), fetched over the *native* HTTP stack, which does
honour the system proxy. Dart HTTP ignores the proxy, so instead of trying to
intercept TLS from Flutter we simply point every absolute HTTP(S) URL in that
config at a plain-HTTP logger running on this machine - the requests then
arrive in clear text.

History:
  * 13.429.1 redirected `*keycloak_login_url`, `*api_url` and `*base_api_url`
    and the app minted its own Keycloak token (client_secret in the snapshot).
  * 13.429.2 dropped `/infosec/.../token` and `client_credentials` from the
    snapshot and added `in_store_offers_secure_proxy_function`; auth moved
    server-side. The rewrite is therefore value-based ("any absolute URL"),
    not key-name-based, so new endpoint keys are covered automatically.
"""
from __future__ import annotations

import json
import logging

from mitmproxy import http

LOGGER_URL = "http://192.168.3.7:9999"

PREFIXES = ("in_store_offers", "hml_in_store_offers")
# Only the keys that carry the API transport. Rewriting "everything that looks
# like a URL" breaks unrelated flows (flyer share links, VTEX sign-in redirects).
TARGET_KEY_TOKENS = (
    "api_url",
    "keycloak_login_url",
    "proxy_function",
    "edge_function",
    "gateway",
)
LOG = r"C:\Android\capture\rc_rewrite.log"


def _log(line: str) -> None:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    if "firebaseremoteconfig" not in host:
        return
    if flow.response is None or flow.response.status_code != 200:
        return
    try:
        data = json.loads(flow.response.get_text(strict=True))
    except Exception as exc:  # noqa: BLE001
        _log(f"nao consegui parsear a resposta de RC: {exc}")
        return

    entries = data.get("entries")
    if not isinstance(entries, dict):
        return

    changed = []
    for key in list(entries):
        if not key.startswith(PREFIXES):
            continue
        if not any(token in key for token in TARGET_KEY_TOKENS):
            continue
        value = entries[key]
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            # e.g. `in_store_offers_secure_proxy_function` is a *name*, not a URL:
            # nothing to redirect here (that is why app >= 13.429.2 escaped us).
            continue
        changed.append(f"{key}: {value} -> {LOGGER_URL}")
        entries[key] = LOGGER_URL
    if not changed:
        return

    flow.response.set_text(json.dumps(data))
    _log("RC reescrito: " + " | ".join(changed))
    logging.warning("RC reescrito: %s", " | ".join(changed))
