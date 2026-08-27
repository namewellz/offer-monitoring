import pytest

from app.catalog.taxonomy import CANONICAL_DEPARTMENTS, canonical_department


@pytest.mark.parametrize(
    ("source_category", "expected"),
    [
        ("AÇOUGUE", "Açougue"),
        ("Carnes, Aves E Peixes", "Açougue"),
        ("Bebidas Alcoólicas", "Bebidas"),
        ("Higiene E Beleza", "Higiene"),
        ("HORTIFRUTIGRANJEIRO", "Hortifruti"),
        ("/Mercearia/Massas/", "Mercearia"),
        ("Mundo Pet", "Pet Shop"),
        ("MAGAZINE", "Bazar e Utilidades"),
    ],
)
def test_source_categories_use_shared_nomenclature(
    source_category: str, expected: str
) -> None:
    assert canonical_department([source_category], "Produto") == expected


@pytest.mark.parametrize(
    ("product_name", "expected"),
    [
        ("Cupim bovino kg", "Açougue"),
        ("Cerveja puro malte lata", "Bebidas"),
        ("Shampoo anticaspa 400ml", "Higiene"),
        ("Detergente líquido neutro", "Limpeza"),
        ("Arroz tipo 1 5kg", "Mercearia"),
    ],
)
def test_product_name_is_fallback_when_source_has_only_ids(
    product_name: str, expected: str
) -> None:
    assert canonical_department(["category:50", "subcategory:2"], product_name) == expected


def test_source_category_has_priority_over_product_name() -> None:
    assert canonical_department(["Frios e Laticínios"], "Bebida láctea") == "Frios e Laticínios"


def test_unknown_product_has_explicit_department() -> None:
    assert canonical_department([], "Produto sem classificação") == "Outros"
    assert {"Açougue", "Bebidas", "Higiene", "Outros"} <= set(CANONICAL_DEPARTMENTS)
