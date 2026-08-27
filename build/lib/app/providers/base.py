from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from app.db.models import FlyerSource


@dataclass(frozen=True)
class DiscoveredPage:
    page_number: int
    url: str


@dataclass(frozen=True)
class DiscoveredFlyer:
    source_url: str
    pages: list[DiscoveredPage]
    source_html: str
    valid_from: date | None = None
    valid_until: date | None = None
    external_id: str | None = None


class FlyerProvider(ABC):
    @abstractmethod
    async def discover(self, source: FlyerSource) -> list[DiscoveredFlyer]: ...

    @abstractmethod
    async def get_pages(self, flyer: DiscoveredFlyer) -> list[DiscoveredPage]: ...
