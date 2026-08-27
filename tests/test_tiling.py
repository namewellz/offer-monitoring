from pathlib import Path

from PIL import Image

from app.extraction.tiling import create_tiles, tile_boxes


def test_four_tiles_overlap_both_centre_lines() -> None:
    boxes = tile_boxes(1000, 800, 20)

    assert boxes == [
        (0, 0, 600, 480),
        (400, 0, 1000, 480),
        (0, 320, 600, 800),
        (400, 320, 1000, 800),
    ]


def test_create_tiles_preserves_page_edges(tmp_path: Path) -> None:
    source = tmp_path / "page.png"
    Image.new("RGB", (1000, 800), "white").save(source)

    tiles = create_tiles(source, tmp_path / "tiles", 20)

    assert len(tiles) == 4
    assert [Image.open(tile.path).size for tile in tiles] == [
        (600, 480),
        (600, 480),
        (600, 480),
        (600, 480),
    ]
