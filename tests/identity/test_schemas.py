from __future__ import annotations

from app.identity.schemas import (
    DEPARTMENT_CODES,
    InterpretationItem,
    department_code_of_label,
    department_label_of_code,
    parse_batch,
    to_json_schema,
)


def test_department_mapping_roundtrip() -> None:
    assert department_code_of_label("Mercearia") == "mercearia"
    assert department_label_of_code("mercearia") == "Mercearia"
    assert department_code_of_label("Bebidas") == "bebidas"
    assert department_code_of_label("  Açougue ") == "acougue"
    assert department_code_of_label("Desconhecido") == "outros"
    assert department_label_of_code("nao-existe") == "Outros"


def test_department_codes_are_closed_and_stable() -> None:
    # Slugs must be accent-free, as produced by the repo's department_code().
    for code, _label in DEPARTMENT_CODES.items():
        assert code == code.casefold()
        assert " " not in code
        assert code in to_json_schema()["properties"]["items"]["additionalProperties"][
            "properties"
        ]["classification"]["properties"]["department_code"]["enum"]


def test_parse_batch_accepts_int_and_string_ids() -> None:
    payload = {
        "items": {
            "1": {
                "id": 1,
                "classification": {
                    "department_code": "bebidas",
                    "family_code": "beer",
                    "product_type": "Cerveja Pilsen",
                },
                "identity": {"brand": "Heineken", "net_quantity": "600", "unit": "ml"},
                "canonical_display_suggestion": "Cerveja Heineken 600 ml",
            }
        }
    }
    items, errors = parse_batch(payload, ["1"])
    assert "1" in items
    assert errors == {}
    assert items["1"].identity.brand == "Heineken"


def test_parse_batch_reports_missing_id() -> None:
    items, errors = parse_batch({"items": {}}, ["42"])
    assert items == {}
    assert errors == {"42": ["ausente na resposta"]}


def test_parse_batch_rejects_bad_department_code() -> None:
    payload = {
        "items": {
            "7": {
                "id": "7",
                "classification": {
                    "department_code": "nao-existe",
                    "family_code": "beer",
                    "product_type": "Cerveja",
                },
                "identity": {},
                "canonical_display_suggestion": None,
            }
        }
    }
    items, errors = parse_batch(payload, ["7"])
    assert "7" in items  # item parseia, mas o erro fica registrado
    assert any("department_code fora da lista" in e for e in errors["7"])


def test_item_lenient_validation_coerces_id() -> None:
    item, errors = InterpretationItem.model_validate_lenient(
        {
            "id": 123,
            "classification": {"department_code": "bebidas"},
            "identity": {},
        },
        "123",
    )
    assert errors == []
    assert item.id == "123"
