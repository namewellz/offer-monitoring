"""Seed configuration for catalog sources and collection targets.

Keeps the API namespace, provider type and per-store codes in one place so a
new store of an already supported source can be registered as configuration
instead of code (section 10.4 of the architecture document). The collectors
still embed some codes today; this registry is the migration surface for moving
them into ``collection_targets``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Abaixo disso nenhum item de supermercado tem preço real: é placeholder de
# indisponibilidade (ex.: R$ 0,01 do Max Atacadista).
MIN_VALID_PRICE_CENTS = 5


@dataclass(frozen=True)
class SourceConfig:
    code: str
    provider_type: str
    # Preços que a API do varejista usa como "sem preço" / fora de estoque.
    # São POR REDE: R$ 999,90 é sentinela no Assaí, mas é preço real de um vinho
    # na Pague Menos.
    sentinel_prices: tuple[str, ...] = ()

    @property
    def sentinel_cents(self) -> frozenset[int]:
        return frozenset(int(round(float(value) * 100)) for value in self.sentinel_prices)


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
    # The VTEX simulation was replaced by the official app's in-store offers API
    # (shelf price plus the app / app+card tiers, per physical branch), so the
    # channel code changed with it: this fork is intentional, the price tiers of
    # the two channels are not comparable.
    "atacadao": SourceConfig("atacadao-app", "atacadao-app-api"),
    "savegnago": SourceConfig("savegnago-vtex", "savegnago-vtex-api"),
    "davitta": SourceConfig("davita-mobilesim-api", "davita-mobilesim-api"),
    "assai": SourceConfig(
        "meu-assai-authenticated-api",
        "assai-authenticated-api",
        # A API devolve 999,9 para produto sem preço/indisponível.
        sentinel_prices=("999.9",),
    ),
    "tenda": SourceConfig("tenda-public-api", "tenda-public-api"),
    "sao-vicente": SourceConfig("saovicente-demandware-api", "saovicente-demandware-api"),
    "max-atacadista": SourceConfig(
        "max-public-api",
        "max-public-api",
        # A API devolve 0,01 quando o item está sem preço no PDV.
        sentinel_prices=("0.01",),
    ),
    "dalben": SourceConfig("dalben-vipcommerce", "dalben-vipcommerce-api"),
    "spani": SourceConfig("spani-vipcommerce", "spani-vipcommerce-api"),
    "pague-menos": SourceConfig(
        "paguemenos-convertiez", "paguemenos-convertiez-api"
    ),
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
    "dalben": TargetDefaults(
        external_store_id="29:1:1",
        external_store_code="superdalben.com.br",
        reference_postal_code="13076-000",
    ),
    "spani": TargetDefaults(
        external_store_id="67:1:42",
        external_store_code="spanionline.com.br",
        reference_postal_code="13060-080",
    ),
    "pague-menos": TargetDefaults(
        external_store_id="60.494.416/0015-30",
        external_store_code="loja-16-rosolen",
        reference_postal_code="13184-222",
    ),
}

COLLECTOR_VERSION = "v2-dual-write-0.1"


def source_config_for(retailer_slug: str) -> SourceConfig:
    return CATALOG_SOURCES[retailer_slug]


def target_defaults_for(retailer_slug: str) -> TargetDefaults:
    return TARGET_DEFAULTS.get(retailer_slug, TargetDefaults())
