from app.providers.base import FlyerProvider

PROVIDERS: dict[str, type[FlyerProvider]] = {}


def register_provider(name: str, provider: type[FlyerProvider]) -> None:
    if not name or name in PROVIDERS:
        raise ValueError(f"Provider already registered or invalid: {name!r}")
    PROVIDERS[name] = provider


from app.providers.goodbom import GoodBomProvider  # noqa: E402

register_provider("goodbom", GoodBomProvider)
