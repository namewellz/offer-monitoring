from app.enrichment.shop_catalog import _group_produce


def _e(pid, price, raw, retailer="atacadao", store="Loja A"):
    return (pid, price, raw, retailer, store)


def test_fuji_presentations_grouped_per_unit_family():
    canonical = {1: "Maçã", 2: "Maçã", 3: "Maçã", 4: "Ovo de Granja"}
    entries = [
        _e(1, 9.98, "Maçã Fuji Kg", "atacadao"),
        _e(2, 6.0, "Maçã Fuji Bandeja 600g", "atacadao"),  # 10/kg
        _e(3, 3.5, "Maçã Fuji Unidade", "tenda"),           # units family
    ]
    lines = _group_produce(entries, canonical)
    by_cat = {(ln["category"], ln["form"]): ln for ln in lines}
    assert ("Maçã Fuji", "kg") in by_cat
    assert ("Maçã Fuji", "un") in by_cat
    kg = by_cat[("Maçã Fuji", "kg")]
    # best per kg across the two mass presentations at atacadao = min(9.98, 10)
    assert round(kg["sources"]["atacadao"]["price"], 2) == 9.98
    un = by_cat[("Maçã Fuji", "un")]
    assert un["sources"]["tenda"]["price"] == 3.5


def test_generic_apple_and_variety_are_separate_rows():
    canonical = {1: "Maçã", 2: "Maçã"}
    entries = [
        _e(1, 8.0, "MAÇÃ IMPORTADA VERMELHA KG"),
        _e(2, 9.98, "Maçã Fuji Kg"),
    ]
    lines = _group_produce(entries, canonical)
    cats = {ln["category"] for ln in lines}
    assert cats == {"Maçã", "Maçã Fuji"}


def test_unmodeled_product_uses_canonical_fallback():
    canonical = {1: "Ovo de Granja"}
    entries = [_e(1, 21.0, "Ovo de Granja 30un")]
    lines = _group_produce(entries, canonical)
    assert [(ln["category"], ln["form"]) for ln in lines] == [("Ovo de Granja", "un")]


def test_raw_without_unit_is_dropped():
    canonical = {1: "Maçã"}
    lines = _group_produce([_e(1, 5.0, "Maçã Fuji")], canonical)
    assert lines == []


def test_unknown_pid_and_no_canonical_dropped():
    canonical = {1: "Maçã"}
    lines = _group_produce([_e(99, 5.0, "produto sem nome de fruta", "x")], canonical)
    assert lines == []


def test_morango_is_package_not_kg():
    canonical = {1: "Morango", 2: "Morango"}
    entries = [
        _e(1, 7.99, "Morango Bandeja 250g", "atacadao"),
        _e(2, 8.9, "Morango Swift 300g Congelado", "tenda"),
    ]
    lines = _group_produce(entries, canonical)
    # any weight/form of Morango is compared as a whole package (R$/pacote)
    assert [(ln["category"], ln["form"]) for ln in lines] == [("Morango", "pacote")]
    row = lines[0]
    assert row["sources"]["atacadao"]["price"] == 7.99
    assert row["sources"]["tenda"]["price"] == 8.9
