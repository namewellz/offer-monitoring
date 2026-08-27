import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.normalization.money import parse_money


class PackageInfo(BaseModel):
    quantity: Decimal | None = None
    unit: str | None = None
    raw_text: str | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def package_quantity(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        match = re.search(r"\d+(?:[.,]\d+)?", value)
        return match.group().replace(",", ".") if match else None


class PriceCondition(BaseModel):
    type: Literal["UNIT_PRICE", "MIN_QUANTITY", "FROM_TO", "LOYALTY_PROGRAM", "CARD", "OTHER"]
    price: Decimal | None = None
    previous_price: Decimal | None = None
    minimum_quantity: int | None = Field(default=None, ge=1, le=999)
    description: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def price_type(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "DE/POR": "FROM_TO",
            "DE_POR": "FROM_TO",
            "DE": "FROM_TO",
            "POR": "FROM_TO",
            "PRECO_UNITARIO": "UNIT_PRICE",
            "PREÇO_UNITÁRIO": "UNIT_PRICE",
            "A_PARTIR_DE": "MIN_QUANTITY",
            "CLUBE": "LOYALTY_PROGRAM",
            "CARTAO": "CARD",
            "CARTÃO": "CARD",
        }
        return aliases.get(normalized, normalized)

    @field_validator("minimum_quantity", mode="before")
    @classmethod
    def quantity(cls, value: object) -> object:
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            value = int(match.group()) if match else None
        return value if isinstance(value, int) and 1 <= value <= 999 else None

    @field_validator("price", "previous_price", mode="before")
    @classmethod
    def money(cls, value: object) -> Decimal | None:
        parsed = parse_money(value)  # type: ignore[arg-type]
        if value is not None and parsed is None:
            raise ValueError("invalid monetary value")
        return parsed


class ExtractedOffer(BaseModel):
    raw_product_name: str = Field(min_length=1)
    normalized_product_name: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    description: str | None = None
    variant: str | None = None
    packages: list[PackageInfo] = Field(default_factory=list)
    prices: list[PriceCondition] = Field(default_factory=list)
    raw_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class FlyerExtraction(BaseModel):
    retailer: str | None = None
    store: str | None = None
    city: str | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    offers: list[ExtractedOffer] = Field(default_factory=list)
