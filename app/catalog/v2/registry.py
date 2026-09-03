"""Seed configuration for catalog sources and collection targets.

Keeps the API namespace, provider type and per-store codes in one place so a
new store of an already supported source can be registered as configuration
instead of code (section 10.4 of the architecture document). The collectors
still embed some codes today; this registry is the migration surface for moving
them into ``collection_targets``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceConfig:
    code: str
    provider_type: str


@dataclass(frozen=True)
class TargetDefaults:
    external_store_id: str | None = None
    external_store_code: str | None = None
    seller_id: str | None = None
    sales_channel: str | None = None
    reference_postal_code: str | None = None


CATALOG_SOURCES: dict[str, SourceConfig] = {
    "arena-atacado": SourceConfig("arena-public-api", "arena-api"),
    "goodbom": SourceConfig("goodbom-mercafacil-api", "goodbom-api"),
    "atacadao": SourceConfig("atacadao-vtex", "atacadao-vtex-api"),
    "savegnago": SourceConfig("savegnago-vtex", "savegnago-vtex-api"),
    "davitta": SourceConfig("davita-mobilesim-api", "davita-mobilesim-api"),
    "assai": SourceConfig("meu-assai-authenticated-api", "assai-authenticated-api"),
    "tenda": SourceConfig("tenda-public-api", "tenda-public-api"),
    "sao-vicente": SourceConfig("saovicente-demandware-api", "saovicente-demandware-api"),
    "max-atacadista": SourceConfig("max-public-api", "max-public-api"),
}

# Codes the collectors still hardcode (README documents each one). The payload
# ``store`` dict overrides these when present.
TARGET_DEFAULTS: dict[str, TargetDefaults] = {
    "tenda": TargetDefaults(
        external_store_code="CT39", reference_postal_code="13184-222"
    ),
    "sao-vicente": TargetDefaults(
        external_store_code="018", reference_postal_code="13184-222"
    ),
    "max-atacadista": TargetDefaults(
        external_store_id="606",
        external_store_code="141",
        reference_postal_code="13184-222",
    ),
    "goodbom": TargetDefaults(reference_postal_code="13184-222"),
}

COLLECTOR_VERSION = "v2-dual-write-0.1"


def source_config_for(retailer_slug: str) -> SourceConfig:
    return CATALOG_SOURCES[retailer_slug]


def target_defaults_for(retailer_slug: str) -> TargetDefaults:
    return TARGET_DEFAULTS.get(retailer_slug, TargetDefaults())
