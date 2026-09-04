from app.enrichment.units import parse_quantity


def _m(name: str) -> float | None:
    parsed = parse_quantity(name)
    return None if parsed is None else parsed.amount_base


def _fam(name: str) -> str | None:
    parsed = parse_quantity(name)
    return None if parsed is None else parsed.family


def test_mass_kg():
    assert abs(_m("Arroz Tipo 1 5kg") - 5.0) < 1e-9
    assert abs(_m("Arroz Branco 5 kg") - 5.0) < 1e-9
    assert abs(_m("Feijão Carioca 1,5kg") - 1.5) < 1e-9
    assert _fam("Arroz Tipo 1 5kg") == "mass"


def test_mass_grams():
    assert abs(_m("Café Torrado 500g") - 0.5) < 1e-9
    assert abs(_m("Biscoito 200 g") - 0.2) < 1e-9
    assert abs(_m("Salgadinho 40g") - 0.04) < 1e-9


def test_volume():
    assert abs(_m("Água com Gás 1,5l") - 1.5) < 1e-9
    assert abs(_m("Refrigerante 2L") - 2.0) < 1e-9
    assert abs(_m("Cerveja Pilsen 350ml") - 0.35) < 1e-9
    assert abs(_m("Suco 900 ml") - 0.9) < 1e-9
    assert _fam("Cerveja 350ml") == "vol"


def test_units():
    assert abs(_m("Fralda Descartável c/ 32 un") - 32.0) < 1e-9
    assert abs(_m("Pilha c/ 4 un") - 4.0) < 1e-9
    assert abs(_m("Absorvente com 8 unidades") - 8.0) < 1e-9
    assert _fam("Pilha c/ 4 un") == "units"


def test_multiplier():
    assert abs(_m("Amendoim 4x100g") - 0.4) < 1e-9
    assert abs(_m("Água 2 x 500ml") - 1.0) < 1e-9


def test_prefers_mass_over_units():
    parsed = parse_quantity("Biscoito Recheado 200g c/ 12 un")
    assert parsed is not None and parsed.family == "mass"
    assert abs(parsed.amount_base - 0.2) < 1e-9


def test_no_unit_returns_none():
    assert parse_quantity("Banana") is None
    assert parse_quantity("Tomate kg") is None  # no numeric qty
    assert parse_quantity("") is None
