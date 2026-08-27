import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.exceptions import AssetDownloadError


@dataclass(frozen=True)
class DownloadedAsset:
    path: Path
    sha256: str
    mime_type: str
    width: int | None
    height: int | None
    file_size: int
    etag: str | None
    last_modified: str | None


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {408, 429} | set(
        range(500, 600)
    )


class DownloadService:
    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(get_settings().http_max_retries),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    async def download(self, url: str, destination: Path) -> DownloadedAsset:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AssetDownloadError(f"Unsafe asset URL: {url}")
        max_size = get_settings().max_asset_size_mb * 1024 * 1024
        try:
            async with httpx.AsyncClient(
                timeout=get_settings().http_timeout_seconds, follow_redirects=True, max_redirects=5
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    declared_size = int(response.headers.get("content-length", "0"))
                    if declared_size > max_size:
                        raise AssetDownloadError("Asset exceeds configured size limit")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > max_size:
                            raise AssetDownloadError("Asset exceeds configured size limit")
        except httpx.HTTPError as exc:
            raise AssetDownloadError(str(exc)) from exc
        try:
            with Image.open(BytesIO(data)) as image:
                normalized = ImageOps.exif_transpose(image)
                width, height = normalized.size
                actual_mime = Image.MIME.get(
                    image.format,
                    response.headers.get("content-type", "application/octet-stream").split(";")[0],
                )
        except OSError as exc:
            raise AssetDownloadError("Downloaded asset is not a supported image") from exc
        suffixes = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/tiff": ".tiff",
        }
        destination = destination.with_suffix(suffixes.get(actual_mime, destination.suffix))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return DownloadedAsset(
            destination,
            hashlib.sha256(data).hexdigest(),
            actual_mime,
            width,
            height,
            len(data),
            response.headers.get("etag"),
            response.headers.get("last-modified"),
        )


def flyer_content_hash(page_hashes: list[str]) -> str:
    return hashlib.sha256("".join(page_hashes).encode()).hexdigest()
