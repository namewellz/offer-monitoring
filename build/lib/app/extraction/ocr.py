from pathlib import Path
from typing import Protocol


class OCRResult:
    pass


class TextExtractor(Protocol):
    async def extract(self, image_path: Path) -> OCRResult: ...


class NoOpTextExtractor:
    async def extract(self, image_path: Path) -> OCRResult:
        return OCRResult()
