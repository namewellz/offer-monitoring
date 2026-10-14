"""Carga e validação do dataset dourado de resolução (spec §18.2).

Layout esperado em ``tests/fixtures/resolution/v1/``:

- ``source_products.jsonl``
- ``canonical_entities.jsonl``
- ``candidate_sets.jsonl``
- ``expected_interpretations.jsonl``
- ``expected_resolutions.jsonl``
- ``pair_labels.jsonl``
- ``README.md``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SOURCE_PRODUCTS_FILE = "source_products.jsonl"
CANONICAL_ENTITIES_FILE = "canonical_entities.jsonl"
CANDIDATE_SETS_FILE = "candidate_sets.jsonl"
EXPECTED_INTERPRETATIONS_FILE = "expected_interpretations.jsonl"
EXPECTED_RESOLUTIONS_FILE = "expected_resolutions.jsonl"
PAIR_LABELS_FILE = "pair_labels.jsonl"

DATASET_FILES = (
    SOURCE_PRODUCTS_FILE,
    CANONICAL_ENTITIES_FILE,
    CANDIDATE_SETS_FILE,
    EXPECTED_INTERPRETATIONS_FILE,
    EXPECTED_RESOLUTIONS_FILE,
    PAIR_LABELS_FILE,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lê um arquivo JSONL, ignorando linhas vazias e comentários ``#``."""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON inválido: {exc}") from exc
    return records


def _index_by(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            raise ValueError(f"registro sem '{key}': {record!r}")
        if value in out:
            raise ValueError(f"'{key}' duplicado: {value!r}")
        out[str(value)] = record
    return out


@dataclass
class ResolutionDataset:
    """Conjunto dourado carregado em memória, com índices por id."""

    source_products: list[dict[str, Any]]
    canonical_entities: list[dict[str, Any]]
    candidate_sets: list[dict[str, Any]]
    expected_interpretations: list[dict[str, Any]]
    expected_resolutions: list[dict[str, Any]]
    pair_labels: list[dict[str, Any]]

    source_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    entity_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    candidates_by_source: dict[str, list[str]] = field(default_factory=dict)
    interpretation_by_source: dict[str, dict[str, Any]] = field(default_factory=dict)
    resolution_by_source: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_resolution_dataset(fixture_dir: str | Path) -> ResolutionDataset:
    """Carrega e valida um diretório de dataset dourado."""
    root = Path(fixture_dir)
    for filename in DATASET_FILES:
        if not (root / filename).exists():
            raise FileNotFoundError(f"dataset incompleto: falta {root / filename}")

    source_products = load_jsonl(root / SOURCE_PRODUCTS_FILE)
    canonical_entities = load_jsonl(root / CANONICAL_ENTITIES_FILE)
    candidate_sets = load_jsonl(root / CANDIDATE_SETS_FILE)
    expected_interpretations = load_jsonl(root / EXPECTED_INTERPRETATIONS_FILE)
    expected_resolutions = load_jsonl(root / EXPECTED_RESOLUTIONS_FILE)
    pair_labels = load_jsonl(root / PAIR_LABELS_FILE)

    dataset = ResolutionDataset(
        source_products=source_products,
        canonical_entities=canonical_entities,
        candidate_sets=candidate_sets,
        expected_interpretations=expected_interpretations,
        expected_resolutions=expected_resolutions,
        pair_labels=pair_labels,
    )
    dataset.source_by_id = _index_by(source_products, "id")
    dataset.entity_by_id = _index_by(canonical_entities, "id")
    dataset.interpretation_by_source = _index_by(expected_interpretations, "source_product_id")
    dataset.resolution_by_source = _index_by(expected_resolutions, "source_product_id")

    for record in candidate_sets:
        dataset.candidates_by_source[str(record["source_product_id"])] = [
            str(cid) for cid in record.get("candidate_ids", [])
        ]

    _validate_references(dataset)
    return dataset


def _validate_references(dataset: ResolutionDataset) -> None:
    """Garante que candidatos e resoluções apontam para entidades/IDs existentes."""
    for source_id in dataset.candidates_by_source:
        if source_id not in dataset.source_by_id:
            raise ValueError(f"candidate_set aponta para source desconhecido: {source_id}")
        for cid in dataset.candidates_by_source[source_id]:
            if cid not in dataset.entity_by_id:
                raise ValueError(f"candidato desconhecido: {cid} (source {source_id})")

    for source_id in dataset.resolution_by_source:
        if source_id not in dataset.source_by_id:
            raise ValueError(f"resolução aponta para source desconhecido: {source_id}")
        canonical_id = dataset.resolution_by_source[source_id].get("canonical_id")
        if canonical_id and canonical_id not in dataset.entity_by_id:
            raise ValueError(f"resolução aponta para canônico desconhecido: {canonical_id}")

    for pair in dataset.pair_labels:
        left, right = pair.get("left_id"), pair.get("right_id")
        if left not in dataset.entity_by_id or right not in dataset.entity_by_id:
            raise ValueError(f"pair_labels com entidade desconhecida: {pair!r}")


def source_ids(dataset: ResolutionDataset) -> list[str]:
    """IDs dos source products em ordem estável de inserção."""
    return [str(record["id"]) for record in dataset.source_products]
