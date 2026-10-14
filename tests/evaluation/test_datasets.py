from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.datasets import (
    ResolutionDataset,
    load_resolution_dataset,
    source_ids,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "resolution" / "v1"


def test_load_resolution_dataset() -> None:
    dataset = load_resolution_dataset(FIXTURE_DIR)
    assert isinstance(dataset, ResolutionDataset)
    assert len(dataset.source_products) == 25
    assert len(dataset.canonical_entities) == 12
    assert len(dataset.candidate_sets) == 9
    assert len(dataset.expected_interpretations) == 25
    assert len(dataset.expected_resolutions) == 9
    assert len(dataset.pair_labels) == 9


def test_source_ids_order_matches_fixture() -> None:
    dataset = load_resolution_dataset(FIXTURE_DIR)
    ids = source_ids(dataset)
    assert ids[0] == "sp:cerveja-heineken-600"
    assert len(ids) == 25
    assert len(set(ids)) == 25


def test_every_source_has_interpretation_golden() -> None:
    dataset = load_resolution_dataset(FIXTURE_DIR)
    for source_id in source_ids(dataset):
        assert source_id in dataset.interpretation_by_source


def test_candidate_sets_reference_known_entities() -> None:
    dataset = load_resolution_dataset(FIXTURE_DIR)
    for _source_id, candidates in dataset.candidates_by_source.items():
        for cid in candidates:
            assert cid in dataset.entity_by_id


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_resolution_dataset(FIXTURE_DIR.parent / "nonexistent")


def test_pair_labels_use_known_entities() -> None:
    dataset = load_resolution_dataset(FIXTURE_DIR)
    for pair in dataset.pair_labels:
        assert pair["left_id"] in dataset.entity_by_id
        assert pair["right_id"] in dataset.entity_by_id
