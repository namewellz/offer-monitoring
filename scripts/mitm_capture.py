"""mitmproxy addon: log all flows to a JSONL file for offline inspection."""
import json
import os
from datetime import datetime, timezone

from mitmproxy import http

LOG_PATH = os.environ.get("MITM_LOG", r"C:\Android\capture\flows.jsonl")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def _safe(text, limit=20000):
    if text is None:
        return None
    try:
        if len(text) > limit:
            return text[:limit] + f"...<truncated {len(text) - limit} chars>"
        return text
    except Exception:
        return "<binary>"


def request(flow: http.HTTPFlow) -> None:
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "request",
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "host": flow.request.host,
            "path": flow.request.path,
            "headers": dict(flow.request.headers),
            "body": _safe(flow.request.get_text(strict=False)),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def response(flow: http.HTTPFlow) -> None:
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "response",
            "url": flow.request.pretty_url,
            "status": flow.response.status_code,
            "content_type": flow.response.headers.get("content-type"),
            "body": _safe(flow.response.get_text(strict=False)),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
