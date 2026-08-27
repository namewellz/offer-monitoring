from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class Tile:
    number: int
    box: tuple[int, int, int, int]
    path: Path


def tile_boxes(width: int, height: int, overlap_percent: int) -> list[tuple[int, int, int, int]]:
    """Return a 2x2 grid expanded around both centre lines.

    The overlap keeps products that cross a quadrant boundary fully visible in at
    least one neighbouring crop, while the outer page edges remain unchanged.
    """
    if width < 2 or height < 2:
        raise ValueError("Image is too small to split into four tiles")
    if not 0 <= overlap_percent <= 40:
        raise ValueError("Tile overlap must be between 0 and 40 percent")

    overlap_x = round(width * overlap_percent / 200)
    overlap_y = round(height * overlap_percent / 200)
    middle_x = width // 2
    middle_y = height // 2
    left_end = min(width, middle_x + overlap_x)
    right_start = max(0, middle_x - overlap_x)
    top_end = min(height, middle_y + overlap_y)
    bottom_start = max(0, middle_y - overlap_y)
    return [
        (0, 0, left_end, top_end),
        (right_start, 0, width, top_end),
        (0, bottom_start, left_end, height),
        (right_start, bottom_start, width, height),
    ]


def create_tiles(image_path: Path, output_dir: Path, overlap_percent: int) -> list[Tile]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        image.load()
        boxes = tile_boxes(image.width, image.height, overlap_percent)
        tiles = []
        for number, box in enumerate(boxes, start=1):
            path = output_dir / f"tile-{number}.jpg"
            crop = image.crop(box)
            if crop.mode not in {"RGB", "L"}:
                crop = crop.convert("RGB")
            crop.save(path, format="JPEG", quality=95, optimize=True)
            tiles.append(Tile(number=number, box=box, path=path))
    return tiles
