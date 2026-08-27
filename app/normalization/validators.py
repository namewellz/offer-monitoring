from decimal import Decimal

VALID_UNITS = {"g", "kg", "ml", "l", "un", "unidade", "pacote", "caixa"}


def validation_confidence(
    name: str, prices: list[Decimal | None], packages: list[str | None]
) -> float:
    score = 0.0
    if name.strip():
        score += 0.4
    if any(price is not None and 0 < price < 100000 for price in prices):
        score += 0.4
    if any(unit and unit.lower() in VALID_UNITS for unit in packages):
        score += 0.2
    return score
