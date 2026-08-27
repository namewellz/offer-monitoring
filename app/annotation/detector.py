from dataclasses import dataclass
from statistics import median

import cv2
import numpy as np


@dataclass
class Anchor:
    x: int
    y: int
    width: int
    height: int
    kind: str


def _red_price_anchors(image: np.ndarray) -> list[Anchor]:
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
            anchors.append(Anchor(x, y, width, height, "OPENCV_RED_PRICE"))
    return anchors


def _light_price_panels(image: np.ndarray) -> list[Anchor]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    _, saturation, value = cv2.split(hsv)
    mask = ((saturation < 60) & (value > 190)).astype("uint8") * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    anchors = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if 60 < width < 220 and 45 < height < 120 and 180 < y < image.shape[0] * 0.68 and area > 3000:
            anchors.append(Anchor(x, y, width, height, "OPENCV_LIGHT_PRICE"))
    return anchors


def _rows(anchors: list[Anchor], tolerance: int = 25) -> list[list[Anchor]]:
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


def _red_regions(image: np.ndarray, anchors: list[Anchor]) -> list[dict]:
    image_height, image_width = image.shape[:2]
    rows = _rows(anchors)
    diffs = [
        right.x - left.x
        for row in rows
        for left, right in zip(row, row[1:])
        if 70 <= right.x - left.x <= 220
    ]
    cell_width = int(median(diffs)) if diffs else image_width // 5
    row_y = [int(median(item.y for item in row)) for row in rows]
    y_diffs = [b - a for a, b in zip(row_y, row_y[1:]) if 65 <= b - a <= 180]
    cell_height = int(median(y_diffs)) if y_diffs else image_height // 9
    result = []
    for row in rows:
        for anchor in row:
            left = max(0, anchor.x - round(cell_width * 0.18))
            top = max(0, anchor.y - round(cell_height * 0.34))
            right = min(image_width, left + cell_width)
            bottom = min(image_height, top + cell_height)
            result.append(
                {
                    "x": round(left * 1000 / image_width),
                    "y": round(top * 1000 / image_height),
                    "width": round((right - left) * 1000 / image_width),
                    "height": round((bottom - top) * 1000 / image_height),
                    "source": anchor.kind,
                    "confidence": 0.7,
                }
            )
    return result


def _light_regions(image: np.ndarray, anchors: list[Anchor]) -> list[dict]:
    image_height, image_width = image.shape[:2]
    result = []
    for anchor in anchors:
        left = max(0, anchor.x - 12)
        right = min(image_width, anchor.x + anchor.width + 12)
        top = max(0, anchor.y - 115)
        bottom = min(image_height, anchor.y + anchor.height + 5)
        result.append(
            {
                "x": round(left * 1000 / image_width),
                "y": round(top * 1000 / image_height),
                "width": round((right - left) * 1000 / image_width),
                "height": round((bottom - top) * 1000 / image_height),
                "source": anchor.kind,
                "confidence": 0.35,
            }
        )
    return result


def propose_regions(image_path: str) -> list[dict]:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Could not read page image")
    red = _red_price_anchors(image)
    result = _red_regions(image, red)
    if len(red) < 5:
        result.extend(_light_regions(image, _light_price_panels(image)))
    return result
