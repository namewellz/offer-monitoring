import json
from json import JSONDecodeError
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.exceptions import FlyerNotFoundError, ParserChangedError, SourceUnavailableError
from app.db.models import FlyerSource
from app.providers.base import DiscoveredFlyer, DiscoveredPage, FlyerProvider


class GoodBomProvider(FlyerProvider):
    """Reads the public flipbook configuration and uses original `src` page assets."""

    async def discover(self, source: FlyerSource) -> list[DiscoveredFlyer]:
        try:
            async with httpx.AsyncClient(
                timeout=get_settings().http_timeout_seconds, follow_redirects=True
            ) as client:
                response = await client.get(source.url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(str(exc)) from exc
        pages = self.parse_pages(response.text, str(response.url))
        if not pages:
            raise FlyerNotFoundError("GoodBom flipbook did not contain page assets")
        return [DiscoveredFlyer(str(response.url), pages, response.text)]

    async def get_pages(self, flyer: DiscoveredFlyer) -> list[DiscoveredPage]:
        return flyer.pages

    @staticmethod
    def parse_pages(html: str, base_url: str) -> list[DiscoveredPage]:
        soup = BeautifulSoup(html, "lxml")
        candidates = [script.get_text() for script in soup.find_all("script")]
        candidates.append(html)
        for text in candidates:
            for value in GoodBomProvider._json_values(text):
                pages = value.get("pages") if isinstance(value, dict) else value
                if not isinstance(pages, list):
                    continue
                found = []
                for index, page in enumerate(pages, start=1):
                    if isinstance(page, dict) and isinstance(page.get("src"), str):
                        number = page.get("title") or page.get("page") or index
                        try:
                            number = int(number)
                        except (TypeError, ValueError):
                            number = index
                        found.append(DiscoveredPage(number, urljoin(base_url, page["src"])))
                if found:
                    return sorted(found, key=lambda page: page.page_number)
        raise ParserChangedError("Could not locate a JSON pages array with original src fields")

    @staticmethod
    def _json_values(text: str):
        decoder = json.JSONDecoder()
        for marker in ('"pages"', "'pages'"):
            start = 0
            while (position := text.find(marker, start)) >= 0:
                array_start = text.find("[", position)
                if array_start < 0:
                    break
                try:
                    yield decoder.raw_decode(text[array_start:])[0]
                except JSONDecodeError:
                    pass
                start = position + len(marker)
