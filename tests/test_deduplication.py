from app.downloader.service import flyer_content_hash
from app.extraction.consolidator import consolidate_offers
from app.extraction.schemas import ExtractedOffer, PriceCondition


def test_content_hash_is_stable_and_ordered() -> None:
    assert flyer_content_hash(["a", "b"]) == flyer_content_hash(["a", "b"])
    assert flyer_content_hash(["a", "b"]) != flyer_content_hash(["b", "a"])


def test_overlapping_tile_offers_are_consolidated() -> None:
    first = ExtractedOffer(
        raw_product_name="Dreamies Petisco para Gatos",
        brand="Dreamies",
        prices=[PriceCondition(type="UNIT_PRICE", price="8,90")],
    )
    second = ExtractedOffer(
        raw_product_name="Petisco para Gatos Dreamies",
        brand="Dreamies",
        prices=[PriceCondition(type="UNIT_PRICE", price="8,90")],
    )
    assert consolidate_offers([first, second]) == [first]
