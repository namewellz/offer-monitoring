"""Canonical hashing for catalog identity and price state.

Implements section 9.2 (``state_hash``) and section 8.2 (``raw_hash`` /
``identity_input_hash``) of docs/CATALOG-COLLECTION-AND-ENRICHMENT.md.

All hashes are SHA-256 digests (32 bytes, stored as ``bytea``). Canonicalization
normalizes lists, deduplicates, orders JSON object keys and converts money to
integer cents before hashing.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

SHA256_LENGTH = 32


def _cents(value: Any) -> int | None:
    """Convert a monetary value to integer cents without float rounding."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return int((value * 100).to_integral_value())
    number = Decimal(str(value))
    return int((number * 100).to_integral_value())


def cents(value: Any) -> int | None:
    """Public helper for integer-cent conversion."""
    return _cents(value)


def _normalized_unit(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _normalized_tags(tags: Any) -> list[str]:
    seen: list[str] = []
    for tag in tags or []:
        text = re.sub(r"\s+", " ", str(tag).strip().casefold())
        if text and text not in seen:
            seen.append(text)
    return sorted(seen)


def _sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        items = [_canonical(item) for item in value]
        return sorted(items, key=_sort_key)
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def digest(value: Any) -> bytes:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).digest()


def price_state(
    *,
    currency: str = "BRL",
    regular_price: Any = None,
    effective_price: Any = None,
    tier_prices: Any = None,
    offer_tags: Any = None,
    measure: Any = None,
    quantity: Any = None,
    unit: Any = None,
) -> dict[str, Any]:
    """Build the canonical price state described in section 9.2.

    Derived fields (discount, previous price, percent) and stock/time/run ids are
    deliberately excluded so unchanged commercial state never creates history.
    """
    tiers: list[dict[str, Any]] = []
    for tier in tier_prices or []:
        if not isinstance(tier, dict):
            continue
        minimum = tier.get("minimum_quantity") or tier.get("quantity")
        price = _cents(tier.get("price"))
        if price is None:
            continue
        tiers.append(
            {
                "minimum_quantity": int(minimum) if minimum is not None else 1,
                "cents": price,
                "condition": str(tier.get("condition") or "quantity"),
            }
        )
    tiers.sort(key=_sort_key)

    conditional_prices = [
        tier["cents"]
        for tier in tiers
        if tier["condition"] in ("club", "app") and tier["cents"] > 0
    ]
    best_conditional = min(conditional_prices) if conditional_prices else None

    return {
        "currency": str(currency or "BRL").upper(),
        "regular_price_cents": _cents(regular_price),
        "effective_price_cents": _cents(effective_price),
        "best_conditional_price_cents": best_conditional,
        "tier_prices": tiers,
        "offer_tags": _normalized_tags(offer_tags),
        "price_basis_unit": _normalized_unit(measure or unit),
        "quantity": _normalized_quantity(quantity),
    }


def _normalized_quantity(value: Any) -> Any:
    if value is None or value == "":
        return None
    number = Decimal(str(value))
    text = format(number, "f").rstrip("0").rstrip(".")
    return text


def price_state_hash(state: dict[str, Any]) -> bytes:
    return digest(state)


def source_product_state(
    *,
    name: Any,
    brand: Any = None,
    gtin: Any = None,
    categories: Any = None,
    measure: Any = None,
    quantity: Any = None,
    unit: Any = None,
    package: Any = None,
    product_url: Any = None,
    raw_attributes: Any = None,
) -> dict[str, Any]:
    # Image is intentionally absent: it is purely presentational (section 8.2).
    return {
        "name": str(name or "").strip(),
        "brand": str(brand).strip() if brand else None,
        "gtin": str(gtin).strip() if gtin else None,
        "categories": [str(c).strip() for c in (categories or []) if c],
        "measure": _normalized_unit(measure),
        "quantity": _normalized_quantity(quantity),
        "unit": _normalized_unit(unit),
        "package": str(package).strip() if package else None,
        "product_url": str(product_url).strip() if product_url else None,
        "raw_attributes": raw_attributes or {},
    }


def identity_input_state(state: dict[str, Any]) -> dict[str, Any]:
    """Drop presentation-only fields (URLs) before hashing identity."""
    return {key: value for key, value in state.items() if key != "product_url"}
