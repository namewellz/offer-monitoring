"""Tests for the Atacadão collector backed by the app's in-store offers API.

The shape of the app payload is documented in
``docs/REVERSE-ENGINEERING-APP-API.md``; these tests pin the mapping decisions
(price tiers, availability semantics, category choice) so a future API change
fails loudly instead of silently degrading the catalog.
"""
from __future__ import annotations

import asyncio
import json

from app.catalog.atacadao import _price, parse_app_products


def _row(**overrides) -> dict:
    row = {
        "idSku": 9975984,
        "idCategoria": 4988,
        "idFilial": 632,
        "idOferta": None,
        "preco": "20.50",
        "finalPrice": None,
        "finalCardPrice": None,
        "discountPercentage": None,
        "discountCardPercentage": None,
        "quantityMax": None,
        "title": "Linguiça Toscana Perdigão Nabrasa 700g",
        "category": "Linguiça",
        "ean": 7891515644437,
        "variablePrice": False,
        "validity": None,
        "status": "",
        "imagem": "https://cdn.example.test/ling.jpg",
    }
    row.update(overrides)
    return row


def test_price_parses_decimal_strings_and_rejects_zero() -> None:
    assert _price("6.98") == 6.98
    assert _price("14,90") == 14.90
    assert _price(None) is None
    assert _price("") is None
    assert _price("0") is None
    assert _price("abc") is None


def test_shelf_price_only_product_has_no_tier() -> None:
    product = parse_app_products([_row()], "Carnes, aves e peixes")[0]
    assert product.id == "9975984"
    assert product.ean == "7891515644437"
    assert product.regular_price == 20.50
    assert product.sales_price == 20.50
    assert product.discount == 0.0
    assert product.tier_prices == []
    assert product.offer_tags == []
    assert product.image_url == "https://cdn.example.test/ling.jpg"


def test_offer_price_becomes_app_tier() -> None:
    product = parse_app_products(
        [_row(finalPrice="16.90", status="DISPONIVEL", idOferta=7636)], "Carnes"
    )[0]
    assert product.regular_price == 20.50
    assert product.sales_price == 16.90
    assert product.discount == 3.60
    assert [(tier.condition, tier.price) for tier in product.tier_prices] == [("app", 16.90)]
    assert product.offer_tags == ["oferta-app"]


def test_card_price_is_an_extra_app_tier() -> None:
    product = parse_app_products(
        [_row(finalPrice="16.90", finalCardPrice="14.50", status="DISPONIVEL")], "Carnes"
    )[0]
    assert product.sales_price == 16.90
    assert [(tier.condition, tier.price) for tier in product.tier_prices] == [
        ("app", 16.90),
        ("app", 14.50),
    ]
    assert product.offer_tags == ["oferta-app", "cartao-atacadao"]


def test_status_is_offer_status_not_availability() -> None:
    """A SKU sold only at the shelf price answers ``status == ""``."""
    shelf_only = parse_app_products([_row(status="")], "Mercearia")[0]
    with_offer = parse_app_products([_row(status="DISPONIVEL", finalPrice="18.00")], "Mercearia")[0]
    assert shelf_only.available is True
    assert with_offer.available is True


def test_unpriced_row_is_not_available() -> None:
    product = parse_app_products([_row(preco=None)], "Mercearia")[0]
    assert product.available is False
    assert product.sales_price is None


def test_leaf_category_wins_and_department_is_a_fallback() -> None:
    leaf_known = parse_app_products([_row(category="Linguiça")], "Frios e congelados")[0]
    assert leaf_known.categories == ["Linguiça"]

    leaf_unknown = parse_app_products(
        [_row(category="Itens de festa", title="Produto sem pista")], "Mercearia"
    )[0]
    assert leaf_unknown.categories == ["Itens de festa", "Mercearia"]

    no_leaf = parse_app_products([_row(category="")], "Bebidas")[0]
    assert no_leaf.categories == ["Bebidas"]


def test_rows_without_sku_or_title_are_skipped() -> None:
    assert parse_app_products([_row(idSku=None), _row(title="  ")], "Mercearia") == []


def test_collect_many_orders_catalogs_by_observation_time(monkeypatch) -> None:
    """The v2 ingest requires increasing timestamps (ck_source_versions_valid_window)."""
    from app.catalog import atacadao

    client = atacadao.AtacadaoCatalogClient()
    stamps = iter(
        [
            "2026-10-14T00:20:00+00:00",
            "2026-10-14T00:10:00+00:00",
            "2026-10-14T00:30:00+00:00",
        ]
    )

    async def fake_collect_store(_client, store):
        payload = client._catalog_payload(store, [], {}, [])
        payload["collected_at"] = next(stamps)
        payload["products"] = [{"id": str(store["filial"]), "name": "x"}]
        return payload

    async def fake_authenticate():
        return "token"

    monkeypatch.setattr(client, "_collect_store", fake_collect_store)
    monkeypatch.setattr(client, "authenticate", fake_authenticate)

    # filiais da allowlist de Campinas: collect_many recusa loja fora dela
    stores = [
        {"name": f"Loja {n}", "filial": n, "city": "c", "state": "SP"} for n in (662, 663, 677)
    ]
    catalogs = asyncio.run(client.collect_many(stores))
    assert [catalog["collected_at"] for catalog in catalogs] == [
        "2026-10-14T00:10:00+00:00",
        "2026-10-14T00:20:00+00:00",
        "2026-10-14T00:30:00+00:00",
    ]


def test_catalog_payload_declares_the_app_channel() -> None:
    from app.catalog.atacadao import AtacadaoCatalogClient

    payload = AtacadaoCatalogClient()._catalog_payload(
        {"name": "Atacadão Hortolândia", "filial": 632, "city": "Hortolândia", "state": "SP"},
        [],
        {},
        [],
    )
    assert payload["store"]["filial"] == 632
    assert payload["store"]["channel"] == "meu-atacadao-app"
    assert "produto/busca" in payload["source"]
    # keeps the payload serialisable for write_catalog
    json.dumps(payload)
