"""mitmproxy addon: rewrite the Remote Config response so the app talks to us.

The app builds its Keycloak token URL from `in_store_offers_keycloak_login_url`
(fetched from Firebase Remote Config over the *native* HTTP stack, which does
honour the system proxy). Dart HTTP ignores the proxy, so instead of trying to
intercept TLS from Flutter we simply point that config value at a plain-HTTP
logger running on this machine - the token request then arrives in clear text.
"""
from __future__ import annotations

import json
import logging

from mitmproxy import http

LOGGER_URL = "http://192.168.3.7:9999"

# only redirect what we need; touching everything would break the rest of the app
# The token endpoint is built from the API base (the app appends
# "/infosec/auth/v1/protocol/openid-connect/token"), so redirect those too.
TARGET_SUBSTRINGS = ("keycloak_login_url", "api_url", "base_api_url")
PREFIXES = ("in_store_offers", "hml_in_store_offers")
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
        if any(token in key for token in TARGET_SUBSTRINGS):
            changed.append(f"{key}: {entries[key]} -> {LOGGER_URL}")
            entries[key] = LOGGER_URL
    if not changed:
        return

    flow.response.set_text(json.dumps(data))
    _log("RC reescrito: " + " | ".join(changed))
    logging.warning("RC reescrito: %s", " | ".join(changed))
