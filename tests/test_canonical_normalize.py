"""Unit tests for app.canonical.normalize (real titles from the v3 prototype CSVs)."""

import pytest

from app.canonical.normalize import (
    ALL_RULES,
    V3_RULES,
    SourceRow,
    build_dictionary,
    gtin_checksum_ok,
    normalize_corpus,
    normalize_row,
    parse_title,
)

BRANDS = ["Yoki", "Scott", "Tirolez", "Danone", "L'Or", "Ypê", "Original", "Flores e Vegetais",
          "Nadir", "Plasutil", "Baly", "Aurora", "Seara", "Bonzo", "Casa Suíça", "Centrum"]


@pytest.fixture(scope="module")
def dictionary():
    rows = [(f"Produto {b} {i}", b) for b in BRANDS for i in range(6)]
    return build_dictionary(rows, ALL_RULES)


def row(name, brand="", retailer="atacadao", cats=(), gtin="", id=1):
    return SourceRow(id, retailer, name, brand, gtin, tuple(cats))


def norm(dictionary, name, brand="", **kw):
    return normalize_row(row(name, brand, **kw), dictionary)


def p(name, dept="Mercearia"):
    return parse_title(name, dept)


# ---- sizes -------------------------------------------------------------------------
def test_kg_without_number_is_one_kg():
    for t in ("Banana Prata kg", "Tomate Italiano a granel", "Carne moida por quilo"):
        x = p(t, "Hortifruti")
        assert (x.size, x.size_src) == ("1000g", "implicit_kg")


def test_dimension_counts_as_size():
    x = p("Prato Descartável Bio Trik Trik Neon Rosa 15cm 10un", "Bazar e Utilidades")
    assert x.size == "dim:15cm" and x.size_src == "dimension"
    assert (x.unit_count, x.unit_type) == (10, "un")


def test_dozen_and_counts_become_unit_packs():
    x = p("Ovos Brancos Dúzia", "Hortifruti")
    assert (x.unit_count, x.unit_type, x.size) == (1, "dz", "1dz")
    x = p("Caderno Fuzy Foroni 160 folhas un", "Bazar e Utilidades")
    assert (x.unit_type, x.unit_count) == ("folha", 160)
    x = p("Papel Higiênico Folha Dupla 12 rolos")
    assert (x.unit_type, x.unit_count, x.size) == ("rolo", 12, "12rolo")
    x = p("Chá Camomila 15 sachês")
    assert x.unit_type == "sache" and x.unit_count == 15
    x = p("Vitamina C 60 cápsulas")
    assert x.unit_type == "capsula" and x.unit_count == 60


def test_multipack_and_pack():
    x = p("Cerveja Original Lata 350ml C/ 12 Unid.", "Bebidas")
    assert x.size == "350ml" and x.unit_count == 12 and x.pkg == "lata"
    x = p("Refrigerante 6x350ml", "Bebidas")
    assert (x.size, x.pack_qty) == ("350ml", 6)


def test_protein_grams_are_ignored():
    x = p("Bebida Láctea 23g Proteínas Yopro Baunilha 250ml", "Bebidas")
    assert x.size == "250ml" and not x.conflict
    x = p("Barra de Cereal 12g de proteína 30g")
    assert x.size == "30g" and not x.conflict


def test_yopro_pro_plus(dictionary):
    assert p("BEBIDA LACTEA YOPRO 15G DOCE DE LEITE HAVANNA 250ML", "Bebidas").size == "250ml"
    x = p("REQUEIJÃO TIROLEZ 17G PRO+ 180G", "Frios e Laticínios")
    assert x.size == "180g" and not x.conflict


def test_gts_range_and_cp():
    x = p("Alimento para Cães Bonzo Carne e Cereais 18kg gts 2kg", "Pet Shop")
    assert x.size == "18000g" and not x.conflict
    x = p("Bolo Casa Suica 350g-370g Clássico Laranja", "Padaria")
    assert x.size == "350g" and not x.conflict
    x = p("Kit Suplemento Centrum Essencial 30CP + 30CP")
    assert (x.unit_count, x.unit_type) == (60, "tablete")
    assert parse_title("Gel 30CP", "Higiene", V3_RULES).unit_count == 0  # v3 proto did not know CP


def test_porta_ovos_duzia_is_not_a_dozen():
    x = p("Porta Ovos Plástico Dúzia Plasutil Decorado", "Bazar e Utilidades")
    assert x.unit_type == "un" and x.unit_count == 1


# ---- brands ------------------------------------------------------------------------
def test_brand_optional_by_department(dictionary):
    x = norm(dictionary, "Banana Prata kg", cats=["Hortifruti"])
    assert (x.brand_origin, x.brand_key) == ("no_brand_ok", "semmarca")
    x = norm(dictionary, "Contra Filé Bovino kg", cats=["Açougue"])
    assert x.brand_origin == "no_brand_ok"
    x = norm(dictionary, "Ovos Brancos Grandes 20 un", cats=["Mercearia"])
    assert x.brand_origin == "no_brand_ok"
    x = norm(dictionary, "Suco Qualquer 1L", cats=["Bebidas"])
    assert x.brand_origin == "none"


def test_egg_rule_only_for_eggs(dictionary):
    x = norm(dictionary, "Ovo de Páscoa Chocolate Surpresa 200g", cats=["Mercearia"])
    assert x.brand_origin == "none"
    x = norm(dictionary, "Porta Ovos Plástico Sanremo", cats=["Mercearia"])
    assert x.brand_origin == "none"


def test_short_brand_whitelist(dictionary):
    x = norm(dictionary, "Detergente Ype Neutro 500ml", cats=["Limpeza"])
    assert x.brand_key == "ype" and x.brand_origin == "inferred"


def test_lor_spelling(dictionary):
    x = norm(dictionary, "Cappuccino Solúvel Lo'r Baunilha 8x20,3g")
    assert x.brand_key == "lor" and x.brand_name == "L'Or"


def test_real_brands_original_and_flores_are_kept(dictionary):
    x = norm(dictionary, "Cerveja Original Lata 350ml", "Original", cats=["Bebidas"])
    assert (x.brand_key, x.brand_origin) == ("original", "source")
    x = norm(dictionary, "Shampoo Flores e Vegetais Matizante 310ml", "FLORES E VEGETAIS")
    assert x.brand_key == "floresevegetais"


def test_invalid_origin_brands_are_dropped(dictionary):
    x = norm(dictionary, "Pimenta bode mape bj 300g", "Generico", cats=["Mercearia"])
    assert x.brand_origin == "no_brand_ok"  # Generico = 'sem marca (não importa)'
    x = norm(dictionary, "Kit Cerveja Ipa com Hambúrguer de Picanha", "Pra Você")
    assert x.brand_origin != "source"


def test_kit_with_two_brands_has_no_brand(dictionary):
    x = norm(dictionary, "Kit Amendoim Yoki 420g com Guardanapos Scott 50 Unidades", "Pra Você")
    assert x.brand_origin == "multi_brand" and x.brand_key == "" and x.parsed.multi
    assert "kit_multi_brand" in x.flags


def test_dalben_davitta_have_no_brand_field(dictionary):
    x = norm(dictionary, "LIMP VEJA X14 TIRA LIMO REFIL 400ML", retailer="davitta")
    assert "retailer_no_brand_field" in x.flags


# ---- groups ------------------------------------------------------------------------
def test_groups_and_review_group_R():
    rows = [
        row("Leite Piracanjuba 1L", "Piracanjuba", "a", id=1),
        row("Leite Piracanjuba 1L", "Piracanjuba", "b", id=2),
        row("Leite Piracanjuba 1L", "Piracanjuba", "c", id=3),
        row("Sabonete Dove 90g", "Dove", "a", id=4),
        row("Caixa Misteriosa Xpto un", "Xpto", "a", gtin="7891000100103", id=5),
        row("Caixa Misteriosa Xpto un", "Xpto", "b", gtin="7891000100103", id=6),
        row("Banana Prata kg", "", "a", cats=["Hortifruti"], id=7),
        row("Coisa sem nada", "", "a", id=8),
    ]
    g = {x.id: x.group for x in normalize_corpus(rows, V3_RULES)}
    assert g[1] == g[2] == g[3] == "A1"
    assert g[4] == "A2"
    assert g[5] == g[6] == "A1" or g[5] == g[6] == "R"
    assert g[7] == "A2"
    assert g[8] == "C"


def test_gtin_with_implicit_one_un_goes_to_R():
    rows = [row("Pilha Fulana Alc un", "Fulana", "a", gtin="7891000100103", id=1),
            row("Pilha Beltrana Pequena un", "Beltrana", "b", gtin="7891000100103", id=2)]
    items = normalize_corpus(rows)
    assert {x.group for x in items} == {"R"}


def test_with_and_without_brand_same_level(dictionary):
    a = norm(dictionary, "Pá de Lixo Plasutil 1 un", "Plasutil")
    b = norm(dictionary, "Pá de Lixo Plasutil 1 un", "")
    assert a.core == b.core and a.parsed.size == b.parsed.size and a.brand_key == b.brand_key


def test_canonical_names(dictionary):
    from app.canonical.normalize import build_canonical_names

    x = norm(dictionary, "Cerveja Original Pilsen 350ml Lata C/ 12 Unid.", "Original", cats=["Bebidas"])
    build_canonical_names(x)
    assert x.canonical_name == "Cerveja Pilsen Original Lata 350 ml Pack 12"
    assert x.canonical_name_no_brand == "Cerveja Pilsen Lata 350 ml Pack 12"


def test_gtin_checksum():
    assert gtin_checksum_ok("7891000100103")
    assert not gtin_checksum_ok("7891000100104")
