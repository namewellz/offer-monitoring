from app.catalog.resilience import collection_metadata, require_products, successful_results


def test_successful_results_separates_failures_without_discarding_values() -> None:
    errors = []

    values = successful_results(
        ["page=1", "page=2", "page=3"],
        [[1], RuntimeError("temporary failure"), [3]],
        errors,
    )

    assert values == [[1], [3]]
    assert errors == [{"scope": "page=2", "error": "RuntimeError: temporary failure"}]
    assert collection_metadata(errors)["collection_status"] == "PARTIAL_SUCCESS"


def test_require_products_only_fails_when_nothing_usable_was_collected() -> None:
    require_products([{"id": 1}], [{"scope": "page=2", "error": "failed"}])
