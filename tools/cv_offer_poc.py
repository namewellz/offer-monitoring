import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

import cv2
import numpy as np


EXPECTED = {1: 26, 2: 45, 3: 44, 4: 20, 5: 16}


@dataclass
class Anchor:
    x: int
    y: int
    width: int
    height: int
    kind: str


@dataclass
class Region:
    id: int
    x: int
    y: int
    width: int
    height: int
    anchor_kind: str


def red_price_anchors(image: np.ndarray) -> list[Anchor]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = cv2.split(hsv)
    mask = (
        (((hue < 10) | (hue > 170)) & (saturation > 130) & (value > 110)).astype("uint8")
        * 255
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    anchors = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        fill = area / (width * height)
        if (
            40 <= width <= 75
            and 13 <= height <= 24
            and 2 <= width / height <= 4.5
            and fill >= 0.65
        ):
            anchors.append(Anchor(x, y, width, height, "red_de_price"))
    return anchors


def light_price_panels(image: np.ndarray) -> list[Anchor]:
    """Fallback for layouts whose price is printed on a light card (e.g. page 5)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    _, saturation, value = cv2.split(hsv)
    mask = ((saturation < 60) & (value > 190)).astype("uint8") * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    anchors = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if 60 < width < 220 and 45 < height < 120 and 180 < y < image.shape[0] * 0.68 and area > 3000:
            anchors.append(Anchor(x, y, width, height, "light_price_panel"))
    return anchors


def group_rows(anchors: list[Anchor], tolerance: int = 25) -> list[list[Anchor]]:
    rows: list[list[Anchor]] = []
    for anchor in sorted(anchors, key=lambda item: (item.y, item.x)):
        for row in rows:
            if abs(anchor.y - median(item.y for item in row)) <= tolerance:
                row.append(anchor)
                break
        else:
            rows.append([anchor])
    for row in rows:
        row.sort(key=lambda item: item.x)
    return rows


def regions_from_red_anchors(image: np.ndarray, anchors: list[Anchor]) -> list[Region]:
    image_height, image_width = image.shape[:2]
    rows = group_rows(anchors)
    all_diffs = [
        right.x - left.x
        for row in rows
        for left, right in zip(row, row[1:])
        if 70 <= right.x - left.x <= 220
    ]
    default_width = int(median(all_diffs)) if all_diffs else image_width // 5
    row_y = [int(median(item.y for item in row)) for row in rows]
    y_diffs = [b - a for a, b in zip(row_y, row_y[1:]) if 65 <= b - a <= 180]
    default_height = int(median(y_diffs)) if y_diffs else image_height // 9
    regions = []
    for row in rows:
        row_diffs = [
            right.x - left.x
            for left, right in zip(row, row[1:])
            if 70 <= right.x - left.x <= 220
        ]
        cell_width = int(median(row_diffs)) if row_diffs else default_width
        for anchor in row:
            left = max(0, anchor.x - round(cell_width * 0.18))
            top = max(0, anchor.y - round(default_height * 0.34))
            right = min(image_width, left + cell_width)
            bottom = min(image_height, top + default_height)
            regions.append(Region(0, left, top, right - left, bottom - top, anchor.kind))
    return regions


def regions_from_light_panels(image: np.ndarray, anchors: list[Anchor]) -> list[Region]:
    image_height, image_width = image.shape[:2]
    regions = []
    for anchor in anchors:
        left = max(0, anchor.x - 12)
        right = min(image_width, anchor.x + anchor.width + 12)
        top = max(0, anchor.y - 115)
        bottom = min(image_height, anchor.y + anchor.height + 5)
        regions.append(Region(0, left, top, right - left, bottom - top, anchor.kind))
    return regions


def detect_regions(image: np.ndarray) -> list[Region]:
    red = red_price_anchors(image)
    regions = regions_from_red_anchors(image, red)
    if len(red) < 5:
        regions.extend(regions_from_light_panels(image, light_price_panels(image)))
    regions.sort(key=lambda item: (item.y, item.x))
    for index, region in enumerate(regions, start=1):
        region.id = index
    return regions


def render(image: np.ndarray, regions: list[Region]) -> np.ndarray:
    output = image.copy()
    line_width = max(2, image.shape[1] // 300)
    font_scale = max(0.45, image.shape[1] / 1400)
    for region in regions:
        right = region.x + region.width
        bottom = region.y + region.height
        cv2.rectangle(output, (region.x, region.y), (right, bottom), (20, 255, 57), line_width)
        label = str(region.id)
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2
        )
        cv2.rectangle(
            output,
            (region.x, region.y),
            (region.x + text_width + 8, region.y + text_height + 8),
            (25, 181, 29),
            -1,
        )
        cv2.putText(
            output,
            label,
            (region.x + 4, region.y + text_height + 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {"method": "opencv_price_anchor_baseline", "pages": []}
    for page, expected in EXPECTED.items():
        source = args.input_dir / f"goodbom-page{page}.jpg"
        image = cv2.imread(str(source))
        if image is None:
            raise FileNotFoundError(source)
        regions = detect_regions(image)
        detected = len(regions)
        count_coverage = min(detected, expected) / expected
        cv2.imwrite(str(args.output_dir / f"page-{page}-detected.jpg"), render(image, regions))
        (args.output_dir / f"page-{page}-regions.json").write_text(
            json.dumps([asdict(region) for region in regions], indent=2), encoding="utf-8"
        )
        report["pages"].append(
            {
                "page": page,
                "expected": expected,
                "detected": detected,
                "count_coverage": round(count_coverage, 4),
            }
        )
    expected_total = sum(item["expected"] for item in report["pages"])
    detected_total = sum(item["detected"] for item in report["pages"])
    report["summary"] = {
        "expected": expected_total,
        "detected": detected_total,
        "count_coverage": round(min(detected_total, expected_total) / expected_total, 4),
        "note": "Count coverage measures anchors only; it is not box precision or IoU.",
    }
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
