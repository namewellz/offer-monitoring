from __future__ import annotations

from app.evaluation.metrics import (
    compute_baseline_metrics,
    compute_interpretation_metrics,
    compute_resolution_metrics,
    department_accuracy,
    field_matches,
    fold,
    token_overlap,
)


def test_fold_normalizes_accents_and_case() -> None:
    assert fold("Cerveja Pilsen") == "cerveja pilsen"
    assert fold("  ÁGUA com Gás ") == "agua com gas"


def test_field_matches_quantity_is_numeric() -> None:
    assert field_matches("2,8", "2.8", "net_quantity")
    assert field_matches("350", "350", "net_quantity")
    assert not field_matches("350", "600", "net_quantity")


def test_field_matches_text_folds() -> None:
    assert field_matches("Heineken", "heineken", "brand")
    assert not field_matches("Heineken", "Brahma", "brand")


def test_token_overlap() -> None:
    assert token_overlap("Cerveja Pilsen", "Cerveja Pilsen") == 1.0
    assert token_overlap("Arroz", "Cerveja") == 0.0


def test_department_accuracy() -> None:
    assert department_accuracy(["a", "b"], ["a", "b"]) == 1.0
    assert department_accuracy(["a", "b"], ["a", "c"]) == 0.5
    assert department_accuracy([], []) == 0.0


def _golden(**overrides) -> dict:
    base = {
        "department_code": "bebidas",
        "family_code": "beer",
        "product_type": "Cerveja Pilsen",
        "brand": "Heineken",
        "net_quantity": "600",
        "unit": "ml",
        "package_type": "garrafa",
        "variant": None,
        "flavor": None,
    }
    base.update(overrides)
    return base


def test_compute_interpretation_metrics_perfect() -> None:
    golden = {"1": _golden()}
    pred = {
        "1": {
            "department_code": "bebidas",
            "family_code": "beer",
            "product_type": "Cerveja Pilsen",
            "brand": "Heineken",
            "net_quantity": "600",
            "unit": "ml",
            "package_type": "garrafa",
            "variant": None,
            "flavor": None,
        }
    }
    metrics = compute_interpretation_metrics(golden, pred, {})
    assert metrics["schema_valid"] == 1
    assert metrics["department_accuracy"] == 1.0
    assert metrics["fields"]["brand"]["accuracy"] == 1.0
    assert metrics["fields"]["package_type"]["accuracy"] == 1.0


def test_compute_interpretation_metrics_counts_schema_failures() -> None:
    golden = {"1": _golden()}
    metrics = compute_interpretation_metrics(golden, {}, {"1": ["ausente na resposta"]})
    assert metrics["schema_valid"] == 0
    assert metrics["schema_invalid"] == 1


def test_compute_interpretation_metrics_detects_invented_field() -> None:
    golden = {"1": _golden(brand=None)}
    pred = {"1": {"brand": "Inventada"}}
    metrics = compute_interpretation_metrics(golden, pred, {})
    assert metrics["invented_fields"].get("brand", 0) == 1


def test_compute_baseline_metrics_perfect() -> None:
    class Dataset:
        source_products = [{"id": "1", "department": "Bebidas"}]
        interpretation_by_source = {"1": {"department_code": "bebidas"}}

    pred = {"1": {"department_code": "bebidas"}}
    metrics = compute_baseline_metrics(Dataset(), pred)
    assert metrics["baseline_vs_golden_accuracy"] == 1.0
    assert metrics["llm_first_vs_golden_accuracy"] == 1.0


def test_compute_resolution_metrics_perfect() -> None:
    expected = {"1": {"action": "MATCH_EXACT", "canonical_id": "t:a"}}
    pred = {"1": {"action": "MATCH_EXACT", "canonical_id": "t:a"}}
    metrics = compute_resolution_metrics(expected, pred)
    assert metrics["action_accuracy"] == 1.0
    assert metrics["canonical_accuracy"] == 1.0
    assert metrics["exact_precision"] == 1.0
