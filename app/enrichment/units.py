"""Parse package quantity/unit from a raw product name (generic).

Used to compare prices across package sizes *per unit* (R$/kg, R$/L, R$/un).
Handles the common Brazilian supermarket patterns:

- "Arroz 5kg", "1,5kg", "500 g", "900ml", "1 L", "2 litros"
- "4x100g", "2 x 500g", "c/ 12 un", "com 10 unidades", "12 un."

Heuristic and intentionally conservative: when the unit cannot be inferred the
parser returns ``None`` (caller drops or flags the item instead of guessing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNIT_TOKENS: dict[str, str] = {}
for _t in ("kg", "kgs", "quilo", "quilos", "kilo", "kilos"):
    _UNIT_TOKENS[_t] = "mass"
for _t in ("g", "gr", "grs", "gramas", "grama", "mg"):
    _UNIT_TOKENS[_t] = "mass"
for _t in ("l", "lt", "litro", "litros", "ml"):
    _UNIT_TOKENS[_t] = "vol"
for _t in (
    "un", "und", "unid", "uni", "unidade", "unidades",
    "pct", "pc", "pç", "un.",
):
    _UNIT_TOKENS[_t] = "units"

# numbers+unit in any position; unit boundaries so "500g" != "0g" inside a word
_RE_QTY_UNIT = re.compile(
    r"(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*(x\s*)?\s*"
    r"(kg|kgs|quilos?|kilos?|g|gr|grs|gramas?|mg|l|lt|litros?|ml|"
    r"un|und|unid|uni|unidade|unidades|pc|pç)\b",
    re.IGNORECASE,
)
# "4x100g" / "2 x 500g": capture multiplier + inner quantity
_RE_MULT = re.compile(
    r"(\d{1,3})\s*[x×]\s*(\d{1,4}(?:[.,]\d{1,3})?)\s*"
    r"(kg|kgs|g|gr|grs|gramas?|mg|l|lt|litros?|ml)\b",
    re.IGNORECASE,
)

_STRIP_UNIT_WORDS = re.compile(r"\b(kg|g|gr|grs|ml|l|lt|un|und|unid|pc)\b\.?", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedUnit:
    # quantity expressed in the family base: kg (mass), L (vol), units
    amount_base: float
    family: str  # "mass" | "vol" | "units"
    display: str  # "kg" | "g" | "L" | "ml" | "un"
    raw: str  # original token, ex.: "5kg"


def _base(amount: float, unit: str) -> tuple[float, str, str]:
    """Return (amount in base unit, family, display)."""
    u = unit.lower().rstrip(".")
    if u in ("kg", "kgs", "quilo", "quilos", "kilo", "kilos"):
        return amount, "mass", "kg"
    if u in ("g", "gr", "grs", "gramas", "grama"):
        return amount / 1000.0, "mass", "g"
    if u == "mg":
        return amount / 1_000_000.0, "mass", "mg"
    if u in ("l", "lt", "litro", "litros"):
        return amount, "vol", "L"
    if u == "ml":
        return amount / 1000.0, "vol", "ml"
    # units
    return amount, "units", "un"


def parse_quantity(name: str) -> ParsedUnit | None:
    """Best-effort parse of the package net quantity/unit from a product name."""
    if not name:
        return None
    # multiplier first: "4x100g" -> 400g ; "2 x 500ml" -> 1000ml
    mult = _RE_MULT.search(name)
    if mult:
        try:
            n1 = int(mult.group(1))
            qty = float(mult.group(2).replace(",", "."))
            amount, family, display = _base(n1 * qty, mult.group(3))
            return ParsedUnit(amount, family, display, mult.group(0))
        except (ValueError, TypeError):
            pass

    matches = list(_RE_QTY_UNIT.finditer(name))
    if not matches:
        return None

    # prefer a mass/volume match; if none, the units match
    def _family(match: re.Match) -> str:
        return _UNIT_TOKENS.get(match.group(3).lower().rstrip("."), "units")

    best: re.Match | None = None
    for match in matches:
        fam = _family(match)
        if best is None:
            best = match
            continue
        fam_best = _family(best)
        # mass/volume beat unit-only tokens (e.g. "un" from "unidade promo")
        if fam in ("mass", "vol") and fam_best == "units":
            best = match
        elif fam == fam_best:
            # larger implied quantity wins (avoid promo "leve 2"... doubles)
            try:
                qty_a = float(match.group(1).replace(",", "."))
                qty_b = float(best.group(1).replace(",", "."))
                if qty_a > qty_b:
                    best = match
            except (ValueError, TypeError):
                pass
    try:
        qty = float(best.group(1).replace(",", "."))
        if best.group(2):  # had an x multiplier before unit (handled above already)
            pass
        amount, family, display = _base(qty, best.group(3))
    except (ValueError, TypeError):
        return None
    if amount <= 0:
        return None
    return ParsedUnit(amount, family, display, best.group(0))


# Categorias vendidas POR PACOTE/EMBALAGEM (não por peso/volume, e não por
# peça): o preço comparável é o do pacote inteiro, sem dividir por nada
# (ex.: Pão de Alho 300g é 1 pacote).
PACKAGE_CATEGORIES: frozenset[str] = frozenset({
    "Pão de Alho",
    "Pão de Queijo",
})


def parse_package_quantity(name: str) -> ParsedUnit:
    """Um pacote/embalagem = 1 unidade de comparação (preço do pacote)."""
    return ParsedUnit(1.0, "package", "pacote", "1 pacote")
