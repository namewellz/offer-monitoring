from app.enrichment.produce import normalize_produce, product_key


def _p(name):
    parsed = normalize_produce(name)
    assert parsed is not None, name
    return parsed


def test_fuji_variants_all_map_to_same_identity():
    """Every presentation/weight of Maçã Fuji -> identity 'Maçã Fuji'."""
    names = [
        "Maçã Fuji Kg",
        "Maçã Fuji 1kg",
        "Maçã Fuji Bandeja 600g",
        "MAÇÃ FUJI PACOTE 2KG",
        "maca fuji bandeja 500g",
    ]
    for name in names:
        p = _p(name)
        assert p.product == "Maçã Fuji", (name, p)
        assert p.variety == "Fuji", (name, p)


def test_pink_lady_multi_word_variety():
    p = _p("Maçã Pink Lady 155g")
    assert p.product == "Maçã Pink Lady"
    assert p.variety == "Pink"


def test_unknown_tokens_fold_to_generic_fruit():
    """Marca/origem/cor must not re-define the product identity."""
    cases = {
        "MAÇÃ PACOTE 1KG": "Maçã",
        "Maçã Argentina Bandeja 720g": "Maçã",
        "Maçã Bulnez Pacote com 850g": "Maçã",
        "MAÇÃ IMPORTADA VERMELHA KG": "Maçã",
        "Maçã Rubifrut 1kg": "Maçã",
        "Maçã Red Importada 18kg": "Maçã",
    }
    for name, expected in cases.items():
        assert _p(name).product == expected, (name, _p(name))


def test_banana_maca_is_banana_variety_not_apple():
    for name in ["Banana Maçã Quilo", "Banana Maçã Kg", "BANANA MACA 1KG"]:
        p = _p(name)
        assert p.fruit == "Banana"
        assert p.product == "Banana Maçã", (name, p)


def test_known_banana_varieties():
    for name, expected in [
        ("Banana Prata Kg", "Banana Prata"),
        ("Banana Nanica 1kg", "Banana Nanica"),
    ]:
        assert _p(name).product == expected, (name,)


def test_weight_and_form():
    p = _p("Maçã Fuji Bandeja 600g")
    assert p.form == "Bandeja"
    assert p.weight_g == 600.0

    p = _p("Maçã Fuji 1kg")
    assert p.form == "Kg"
    assert p.weight_g == 1000.0

    p = _p("Maçã Red Importada 18kg")
    assert p.weight_g == 18000.0


def test_unknown_fruit_returns_none():
    assert normalize_produce("Arroz 5kg") is None
    assert normalize_produce("") is None


def test_product_key_groups_across_presentations():
    keys = {product_key(n) for n in [
        "Maçã Fuji 1kg",
        "Maçã Fuji Bandeja 600g",
        "maca fuji kg",
    ]}
    assert keys == {"maca fuji"}
