from __future__ import annotations

from app.identity.fingerprints import (
    canonical_json,
    commercial_fingerprint,
    identity_fingerprint,
    request_hash,
    sha256_hex,
)


def _identity(**overrides) -> dict:
    base = {
        "name": "Cerveja Heineken 600ml",
        "brand": "Heineken",
        "gtin": None,
        "categories": ["Bebidas"],
        "description": None,
        "measure": "UN",
        "quantity": None,
        "unit": None,
        "package": None,
        "identity_attributes": {},
        # campos que NÃO devem entrar no fingerprint de identidade
        "store_id": "x",
        "regular_price_cents": 599,
        "effective_price_cents": 499,
        "available": True,
        "stock": 10,
        "price_terms": [],
    }
    base.update(overrides)
    return base


def test_canonical_json_sorts_keys() -> None:
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_identity_fingerprint_ignores_price_and_stock() -> None:
    first = identity_fingerprint(_identity())
    changed_price = identity_fingerprint(_identity(effective_price_cents=399, stock=0))
    assert first == changed_price


def test_identity_fingerprint_changes_with_quantity() -> None:
    first = identity_fingerprint(_identity())
    changed = identity_fingerprint(_identity(quantity="350", unit="ml"))
    assert first != changed


def test_commercial_fingerprint_changes_with_price() -> None:
    first = commercial_fingerprint(_identity())
    changed = commercial_fingerprint(_identity(effective_price_cents=399))
    assert first != changed


def test_request_hash_is_sensitive_to_versions_and_candidates() -> None:
    fp = identity_fingerprint(_identity())
    base = request_hash(
        fp,
        model="deepseek-chat",
        prompt_version="v1",
        schema_version="s1",
        policy_version="p1",
        candidates=["t:a", "t:b"],
    )
    assert base != request_hash(
        fp,
        model="deepseek-chat",
        prompt_version="v2",
        schema_version="s1",
        policy_version="p1",
        candidates=["t:a", "t:b"],
    )
    assert base != request_hash(
        fp,
        model="deepseek-chat",
        prompt_version="v1",
        schema_version="s1",
        policy_version="p1",
        candidates=["t:a", "t:c"],
    )
    # conjunto de candidatos é ordenado antes do hash
    same = request_hash(
        fp,
        model="deepseek-chat",
        prompt_version="v1",
        schema_version="s1",
        policy_version="p1",
        candidates=["t:b", "t:a"],
    )
    assert base == same


def test_sha256_hex_is_stable() -> None:
    assert sha256_hex("abc") == sha256_hex("abc")
    assert len(sha256_hex("abc")) == 64
