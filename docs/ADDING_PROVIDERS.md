# Adding a supermarket provider

A provider is responsible only for discovering flyers and returning the original page URLs. Downloading, deduplication, queueing, extraction and persistence are shared services.

1. Create `app/providers/<name>.py` with a class implementing `FlyerProvider`.
2. Return one `DiscoveredFlyer` per flyer. Include `valid_from`, `valid_until` and `external_id` whenever the source exposes them.
3. Register the class in `app/providers/__init__.py` with a stable lowercase name.
4. Add a `FlyerSource` whose `provider_type` is that same name.
5. Add offline parser fixtures and tests. Network tests must use the `external` marker.

Providers must use public source assets, resolve relative URLs, raise an explicit error when the upstream layout changes, and must not write files or access the database directly.

Example:

```python
class MarketProvider(FlyerProvider):
    async def discover(self, source: FlyerSource) -> list[DiscoveredFlyer]:
        html = await self.fetch(source.url)
        pages = self.parse_pages(html, source.url)
        return [DiscoveredFlyer(source.url, pages, html)]

    async def get_pages(self, flyer: DiscoveredFlyer) -> list[DiscoveredPage]:
        return flyer.pages
```

Then add `register_provider("market", MarketProvider)` to the provider registry.
