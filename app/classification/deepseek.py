"""DeepSeek online chat client (OpenAI-compatible) for product classification.

Local Ollama is intentionally NOT used here: the user wants the classification
done by the hosted DeepSeek API (model ``deepseek-chat`` by default). The client
is synchronous (httpx) so it can run inside RQ workers or plain scripts.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings


class DeepSeekError(RuntimeError):
    """Raised when the DeepSeek API cannot be used or returns bad output."""


class DeepSeekClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.deepseek_base_url.rstrip("/")
        self.model = self.settings.deepseek_model
        secret = self.settings.deepseek_api_key
        self._key = secret.get_secret_value() if secret is not None else None

    @property
    def ready(self) -> bool:
        return bool(self._key)

    def _ensure_key(self) -> None:
        if not self._key:
            raise DeepSeekError(
                "DEEPSEEK_API_KEY não configurada. Adicione no .env "
                "(DEEPSEEK_API_KEY=sk-...) e reinicie o processo."
            )

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(get_settings().deepseek_max_retries),
        wait=wait_exponential(min=1.5, max=20),
        reraise=True,
    )
    def chat_json(self, system: str, user: str) -> str:
        """Single chat completion expecting a JSON object in the answer."""
        self._ensure_key()
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.settings.deepseek_temperature,
            "max_tokens": 8192,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        try:
            payload["response_format"] = {"type": "json_object"}
        except Exception:
            pass
        try:
            with httpx.Client(
                timeout=self.settings.deepseek_request_timeout_seconds
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:400] if exc.response is not None else ""
            raise DeepSeekError(f"DeepSeek HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise DeepSeekError(f"DeepSeek request failed: {exc}") from exc
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise DeepSeekError(f"Resposta inesperada da DeepSeek: {exc}") from exc
        return _extract_json(content)


def _extract_json(content: str) -> str:
    """Strip markdown fences/trailing text so the answer is a bare JSON object."""
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.DOTALL)
    if fence:
        content = fence.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]
    return content


def parse_ids_json(content: str, provided_ids: set[int]) -> tuple[dict[int, str], dict[int, str]]:
    """Parse {"accepted_ids":[...],"rejected_ids":[...],"reasons":{...}}.

    Every provided id must appear in exactly one list. Returns
    ``(decisions, reasons)`` where decisions maps product_id to ``accept`` or
    ``reject`` and reasons maps product_id to a short human note (when given).
    """
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeepSeekError(f"Resposta da LLM não é JSON válido: {content[:300]}") from exc

    def _ids(key: str) -> set[int]:
        values = payload.get(key) or []
        out: set[int] = set()
        for value in values:
            try:
                out.add(int(value))
            except (TypeError, ValueError):
                continue
        return out

    accepted = _ids("accepted_ids")
    rejected = _ids("rejected_ids")
    raw_reasons = payload.get("reasons") or {}

    reasons: dict[int, str] = {}
    for key, value in raw_reasons.items():
        try:
            reasons[int(key)] = str(value)
        except (TypeError, ValueError):
            continue

    decisions: dict[int, str] = {}
    for pid in provided_ids:
        if pid in accepted and pid not in rejected:
            decisions[pid] = "accept"
        elif pid in rejected and pid not in accepted:
            decisions[pid] = "reject"
        elif pid in accepted:
            # appears in both -> accept wins
            decisions[pid] = "accept"
        else:
            # not mentioned at all: safest is reject (the model did not read it
            # as the real product)
            decisions[pid] = "reject"
    return decisions, reasons


def parse_categories(content: str) -> dict[int, tuple[str, str]]:
    """Parse the Açougue reply: {"items": {"<id>": {"category","note"}}}.

    Returns ``{product_id: (category, note)}``. A missing category is kept as
    ``NAO_CARNE`` so every product still gets a verdict.
    """
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeepSeekError(f"Resposta da LLM não é JSON válido: {content[:300]}") from exc
    raw_items = payload.get("items")
    if not isinstance(raw_items, dict):
        raise DeepSeekError("Resposta sem o campo 'items' (objeto id→categoria).")

    out: dict[int, tuple[str, str]] = {}
    for key, value in raw_items.items():
        try:
            pid = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            out[pid] = ("NAO_CARNE", "")
            continue
        category = str(value.get("category") or "NAO_CARNE").strip() or "NAO_CARNE"
        note = str(value.get("note") or "").strip()
        out[pid] = (category, note)
    return out
