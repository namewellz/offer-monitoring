"""Unit tests for the Açougue deterministic parser."""

from app.enrichment.meat import parse_meat


def test_peito_frango_sem_osso() -> None:
    parsed = parse_meat("PEITO FRANGO S/OSSO GRANEL KG")
    assert parsed.species == "frango"
    assert parsed.cut == "peito"
    assert parsed.bone_state == "sem_osso"
    assert parsed.sale_mode == "kg"


def test_contra_file_com_osso() -> None:
    parsed = parse_meat("BOV CONTRA FILE C/ OSSO (BISTEC")
    assert parsed.species == "bovino"
    assert parsed.cut == "contra_file"
    assert parsed.bone_state == "com_osso"


def test_acem_sem_osso_em_cubos() -> None:
    parsed = parse_meat("Acém Bovino Sem Osso Em Cubos Reserva Bandeja Kg")
    assert parsed.species == "bovino"
    assert parsed.cut == "acem"
    assert parsed.bone_state == "sem_osso"
    assert parsed.presentation == "cubos"
    assert parsed.sale_mode == "kg"


def test_asa_congelada_peso_fixo() -> None:
    parsed = parse_meat("Asa de Frango Congelada 1kg")
    assert parsed.species == "frango"
    assert parsed.cut == "asa"
    assert parsed.conservation == "congelado"
    assert parsed.sale_mode == "peso_fixo"
    assert parsed.weight_kg == 1.0


def test_asa_congelada_por_quilo() -> None:
    parsed = parse_meat("Asa de Frango Congelada Pacote Kg")
    assert parsed.species == "frango"
    assert parsed.cut == "asa"
    assert parsed.sale_mode == "kg"


def test_bisteca_suina_com_couro() -> None:
    parsed = parse_meat("Bisteca Suína Com Couro Bandeja Kg")
    assert parsed.species == "suino"
    assert parsed.cut == "bisteca"
    assert parsed.skin_state == "com_pele"
    assert parsed.sale_mode == "kg"


def test_carne_moida_peso_fixo() -> None:
    parsed = parse_meat("Carne Moída Bovina Friboi Congelada Pacote 500g")
    assert parsed.species == "bovino"
    assert parsed.cut == "carne_moida"
    assert parsed.conservation == "congelado"
    assert parsed.sale_mode == "peso_fixo"
    assert parsed.weight_kg == 0.5


def test_picanha() -> None:
    parsed = parse_meat("BOV PICANHA FRIBOI KG")
    assert parsed.species == "bovino"
    assert parsed.cut == "picanha"
    assert parsed.sale_mode == "kg"
    assert parsed.brand == "friboi"


def test_costela_minga_subcut() -> None:
    parsed = parse_meat("Costela Minga Bovina Bandeja Kg")
    assert parsed.species == "bovino"
    assert parsed.cut == "costela_minga"


def test_non_meat_pet_food() -> None:
    parsed = parse_meat("Alim p/ caes pedigree 100g carne molho")
    assert not parsed.is_meat
    assert "non_meat" in parsed.flags


def test_temperado() -> None:
    parsed = parse_meat("Ancho Suíno Seara Cong Ao Chimichurri Preço por quilo na peça")
    assert parsed.species == "suino"
    assert parsed.cut == "ancho"
    assert parsed.seasoned is True
    assert parsed.sale_mode == "kg"


def test_variant_key_ignores_brand_and_sale_mode() -> None:
    a = parse_meat("Asa de Frango Copacol Congelada 1kg")
    b = parse_meat("Asa de Frango Sadia Congelada 1kg")
    assert a.variant_key == b.variant_key
