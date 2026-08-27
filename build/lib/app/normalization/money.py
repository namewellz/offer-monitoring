import re
from decimal import Decimal, InvalidOperation


def parse_money(value: str | Decimal | int | float | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            result = Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
        return result if Decimal("0") < result < Decimal("100000") else None
    text = re.sub(r"[^0-9,.-]", "", str(value)).replace(".", "").replace(",", ".")
    try:
        result = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return result if Decimal("0") < result < Decimal("100000") else None
