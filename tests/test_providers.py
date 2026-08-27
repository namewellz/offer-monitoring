import pytest

from app.providers import PROVIDERS, register_provider
from app.providers.base import FlyerProvider


class ExampleProvider(FlyerProvider):
    async def discover(self, source):
        return []

    async def get_pages(self, flyer):
        return flyer.pages


def test_goodbom_is_registered() -> None:
    assert "goodbom" in PROVIDERS


def test_provider_names_cannot_be_overwritten() -> None:
    name = "test-provider"
    register_provider(name, ExampleProvider)
    try:
        with pytest.raises(ValueError):
            register_provider(name, ExampleProvider)
    finally:
        PROVIDERS.pop(name)
