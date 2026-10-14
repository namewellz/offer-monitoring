"""Logging reverse proxy that stands in for the in-store offers API.

The patched Remote Config points the module's base URLs at this server over
plain HTTP, so every Dart request arrives here unencrypted. Each request is
logged and then forwarded to the real upstream (freyr for the offers API,
skadi for Keycloak), so the app keeps working exactly as it would normally -
including receiving the genuine 401s that make it fetch a token, which is the
request that carries the client_secret.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path(r"C:\Android\capture\token_requests.jsonl")
PORT = 9999

FREYR = "https://freyr.portal.atacadao.com.br"
SKADI = "https://skadi-prod.portal.atacadao.com.br"
HOP_BY_HOP = {
    "host", "content-length", "connection", "accept-encoding", "transfer-encoding",
    "keep-alive", "proxy-connection", "upgrade",
}
CTX = ssl.create_default_context()


def upstream_for(path: str) -> str:
    if path.startswith("/realms/") or path.startswith("/resources/"):
        return SKADI
    return FREYR


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        base = upstream_for(self.path)
        target = base + self.path
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Accept-Encoding"] = "identity"

        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "method": self.command,
            "path": self.path,
            "upstream": target,
            "headers": dict(self.headers),
            "body": body.decode("utf-8", "replace"),
        }
        print(f"--> {self.command} {target}", flush=True)
        if body:
            print("    body:", body.decode("utf-8", "replace")[:600], flush=True)

        status, payload, ctype = 502, b'{"error":"upstream failed"}', "application/json"
        try:
            req = urllib.request.Request(target, data=body or None, headers=headers, method=self.command)
            with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
                status = resp.status
                payload = resp.read()
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            ctype = exc.headers.get("Content-Type", "application/json") if exc.headers else "application/json"
        except Exception as exc:  # noqa: BLE001
            entry["proxy_error"] = str(exc)

        entry["status"] = status
        entry["response"] = payload.decode("utf-8", "replace")[:4000]
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"<-- {status} ({len(payload)} bytes)", flush=True)

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_PATCH = _handle

    def log_message(self, *args) -> None:  # silence default access log
        return


if __name__ == "__main__":
    print(f"proxy reverso de log em 0.0.0.0:{PORT} -> {LOG}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
