"""Group parsed meat items into comparable variants and compute price per kg."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.enrichment.meat import ParsedMeat, parse_meat


@dataclass
class MeatItem:
    retailer: str
    store: str | None
    product_id: int
    raw_name: str
    effective_price_cents: int | None = None
    parsed: ParsedMeat = field(init=False)

    def __post_init__(self) -> None:
        self.parsed = parse_meat(self.raw_name)

    @property
    def price_kg(self) -> Decimal | None:
        """Price per kg in reais; None when not comparable by kg."""
        if self.effective_price_cents is None:
            return None
        price = Decimal(self.effective_price_cents) / 100
        mode = self.parsed.sale_mode
        if mode == "kg":
            return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if mode == "peso_fixo" and self.parsed.weight_kg:
            return (price / Decimal(str(self.parsed.weight_kg))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return None


def group_comparable(items: list[MeatItem]) -> list[dict[str, Any]]:
    """Group items by variant key and expose the cheapest price per kg per source."""
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        key = item.parsed.variant_key
        if key is None:
            continue
        group = groups.setdefault(
            key,
            {
                "variant_key": list(key),
                "species": item.parsed.species,
                "cut": item.parsed.cut,
                "label": item.parsed.label,
                "bone_state": item.parsed.bone_state,
                "skin_state": item.parsed.skin_state,
                "presentation": item.parsed.presentation,
                "conservation": item.parsed.conservation,
                "seasoned": item.parsed.seasoned,
                "sources": {},
            },
        )
        price_kg = item.price_kg
        entry = group["sources"].setdefault(item.retailer, {"price_kg": None, "sample": None})
        if price_kg is not None and (
            entry["price_kg"] is None or price_kg < entry["price_kg"]
        ):
            entry["price_kg"] = price_kg
            entry["sample"] = item.raw_name
    return list(groups.values())
