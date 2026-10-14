"""Fingerprints e hashes de identidade/comercial (spec §5).

Os fingerprints são a memória barata do pipeline: permitem reutilizar uma
interpretação quando o conteúdo relevante não mudou e, ao mesmo tempo,
invalidar o cache quando mudar a identidade, o prompt, o modelo, a política ou
o conjunto de candidatos.

Três hashes independentes:

- ``identity_fingerprint``: campos capazes de alterar a identidade do produto.
  Preço e estoque NÃO entram aqui.
- ``commercial_fingerprint``: preço, estoque, disponibilidade e condições.
  Mudanças comerciais nunca chamam a LLM.
- ``request_hash``: combina identidade + versões do pipeline + conjunto de
  candidatos. É a chave de cache da interpretação/resolução.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

# Campos que participam da identidade recebida da fonte (spec §5.4).
IDENTITY_FIELDS = (
    "name",
    "brand",
    "gtin",
    "categories",
    "description",
    "measure",
    "quantity",
    "unit",
    "package",
    "identity_attributes",
)

# Campos que participam do estado comercial (spec §5.5).
COMMERCIAL_FIELDS = (
    "store_id",
    "currency",
    "regular_price_cents",
    "effective_price_cents",
    "available",
    "stock",
    "price_terms",
    "valid_until",
)


def canonical_json(value: Any) -> str:
    """Serialização canônica de um objeto (spec §5.2).

    - Unicode NFKC;
    - ``None`` vira ``null``;
    - chaves ordenadas recursivamente;
    - separadores sem espaço para estabilidade do hash.
    """
    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    if isinstance(value, dict):
        return {_canonicalize(k): _canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    # Outros tipos (datas, enums) caem para a representação estável possível.
    return str(value)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _subset_fingerprint(mapping: dict[str, Any], fields: tuple[str, ...]) -> str:
    subset = {field: mapping.get(field) for field in fields}
    return sha256_hex(canonical_json(subset))


def identity_fingerprint(raw_identity: dict[str, Any]) -> str:
    """SHA-256 da identidade recebida (campos de identidade apenas)."""
    return _subset_fingerprint(raw_identity, IDENTITY_FIELDS)


def commercial_fingerprint(raw_commercial: dict[str, Any]) -> str:
    """SHA-256 do estado comercial (não chama a LLM quando muda)."""
    return _subset_fingerprint(raw_commercial, COMMERCIAL_FIELDS)


def candidate_set_hash(canonical_ids: list[str]) -> str:
    """Hash do conjunto de candidatos apresentado ao resolvedor (ordem estável)."""
    return sha256_hex(canonical_json(sorted(str(cid) for cid in canonical_ids)))


def request_hash(
    identity_fp: str,
    *,
    model: str,
    prompt_version: str,
    schema_version: str,
    policy_version: str,
    candidates: list[str],
) -> str:
    """Chave de cache da inferência/resolução (spec §5.6).

    Inclui o conjunto de candidatos para que o crescimento do catálogo
    canônico possa reavaliar um produto sem reprocessar a interpretação bruta.
    """
    payload = {
        "identity_fingerprint": identity_fp,
        "model": model,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "policy_version": policy_version,
        "candidate_set_hash": candidate_set_hash(candidates),
    }
    return sha256_hex(canonical_json(payload))
