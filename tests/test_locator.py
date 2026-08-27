from pathlib import Path

from PIL import Image

from app.extraction.locator import LocatedOffers, OfferRegion, render_regions


def test_region_must_stay_inside_normalized_page() -> None:
    region = OfferRegion(id=1, x=100, y=200, width=300, height=400)
    assert region.x + region.width == 400


def test_render_regions_keeps_original_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "page.jpg"
    output = tmp_path / "marked.jpg"
    Image.new("RGB", (500, 700), "navy").save(source)
    render_regions(
        source,
        LocatedOffers(regions=[OfferRegion(id=1, x=100, y=100, width=200, height=300)]),
        output,
    )
    assert Image.open(output).size == (500, 700)
