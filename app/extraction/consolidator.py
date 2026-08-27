from rapidfuzz.fuzz import token_sort_ratio

from app.extraction.schemas import ExtractedOffer


def consolidate_offers(
    offers: list[ExtractedOffer], similarity: float = 90
) -> list[ExtractedOffer]:
    """Keeps one deterministic representative for overlapping tile results."""
    result: list[ExtractedOffer] = []
    for offer in offers:
        name = offer.normalized_product_name or offer.raw_product_name
        prices = {price.price for price in offer.prices if price.price is not None}
        duplicate = any(
            token_sort_ratio(name, existing.normalized_product_name or existing.raw_product_name)
            >= similarity
            and prices == {price.price for price in existing.prices if price.price is not None}
            and (offer.brand or "").casefold() == (existing.brand or "").casefold()
            for existing in result
        )
        if not duplicate:
            result.append(offer)
    return result
