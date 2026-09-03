"""Text utilities for the deterministic enrichment engine."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")


def fold(value: str) -> str:
    """Lowercase, strip accents and collapse whitespace for matching."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    return _WS.sub(" ", value).strip()


def ascii_slug(value: str) -> str:
    """Fold and replace non-alphanumerics with single spaces."""
    value = fold(value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def expand(text: str, dictionary: dict[str, str]) -> str:
    """Replace whole-word abbreviations using a mapping (keys are folded)."""
    words = text.split()
    out: list[str] = []
    for word in words:
        expanded = dictionary.get(word, word)
        out.append(expanded)
    return " ".join(out)


def number(value: str) -> float | None:
    value = (value or "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None
