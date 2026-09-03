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


# --- linguiça "tipo/linha" splits into its own families -----------------------

def test_linguica_calabresa_tipo() -> None:
    parsed = parse_meat("LING CALABRESA SADIA KG")
    assert parsed.cut == "linguica"
    assert parsed.cut_type == "calabresa"
    assert parsed.species == "suino"
    assert parsed.label == "Linguiça Calabresa"


def test_linguica_calab_tipo_dot_abbreviation() -> None:
    parsed = parse_meat("LINGUIÇA  TIPO CAL.ABRESA PERDIGÃO 400G")
    assert parsed.cut_type == "calabresa"


def test_linguica_fininha() -> None:
    parsed = parse_meat("LINGUIÇA FININHA PERDIGÃO 215G")
    assert parsed.cut_type == "fininha"


def test_linguica_aperitivo_eh_fininha() -> None:
    parsed = parse_meat("LINGUIÇA APERITIVO MARCHIORI APIMENTADA KG")
    assert parsed.cut_type == "fininha"


def test_linguica_pernil_fina_eh_fininha() -> None:
    parsed = parse_meat("LINGUIÇA PERNIL FINA CATABY KG")
    assert parsed.cut_type == "fininha"


def test_linguica_paio() -> None:
    parsed = parse_meat("LINGUIÇA TIPO PAIO SADIA 370G")
    assert parsed.cut_type == "paio"


def test_linguica_vegana_soja() -> None:
    parsed = parse_meat("LINGUIÇA DE SOJA VEGGIE 300G")
    assert parsed.is_meat
    assert parsed.species == "vegetal"
    assert parsed.cut_type == "vegana"
    assert parsed.label == "Linguiça Vegana"


def test_linguica_vegana_vegetal() -> None:
    parsed = parse_meat("Linguiça Vegetal Futuro 250g")
    assert parsed.species == "vegetal"
    assert parsed.label == "Linguiça Vegana"


def test_linguica_toscana_soja_eh_vegana() -> None:
    parsed = parse_meat("LINGUIÇA TOSCANA DE SOJA VEGGES 300G")
    assert parsed.species == "vegetal"


# --- bacon as flavour of non-meat is NOT a meat cut ---------------------------

def test_bacon_flavor_amendoim_non_meat() -> None:
    parsed = parse_meat("AMENDOIM MENDORATO BACON C/MAPLE 90G")
    assert not parsed.is_meat
    assert "non_meat" in parsed.flags


def test_bacon_flavor_biscoito_non_meat() -> None:
    parsed = parse_meat("Biscoito Club Social Regular Bacon & Provolone 141g")
    assert not parsed.is_meat


def test_bacon_flavor_salgadinho_non_meat() -> None:
    parsed = parse_meat("SALGADINHO FABITOS SABOR BACON 90G")
    assert not parsed.is_meat


def test_bacon_flavor_pet_bifinho_non_meat() -> None:
    parsed = parse_meat("Bifinho para Cães Petiscão Bacon 60g")
    assert not parsed.is_meat


def test_bacon_petisco_canino_non_meat() -> None:
    parsed = parse_meat("Biscoito De Polvilho Cassini Bacon 80g")
    assert not parsed.is_meat


def test_bacon_real_continues_to_be_cut() -> None:
    parsed = parse_meat("Bacon Defumado Aurora 200g")
    assert parsed.cut == "bacon"
    assert parsed.species == "suino"


def test_bacon_ingredient_in_linguica_frango() -> None:
    parsed = parse_meat("Linguiça de Frango com Bacon Premium Aurora 500g")
    assert parsed.cut == "linguica"
    assert parsed.species == "frango"
    assert parsed.cut != "bacon"


# --- prepared products (choripan/espetinho/empanado/hambúrguer) ---------------

def test_choripan_com_linguica_prepared() -> None:
    parsed = parse_meat("Choripan com Linguiça Toscana e Queijo Aurora 400g")
    assert not parsed.is_meat
    assert "prepared" in parsed.flags


def test_espetinho_linguica_prepared() -> None:
    parsed = parse_meat("Espetinho Linguiça Swift 500g Apimentada")
    assert not parsed.is_meat
    assert "prepared" in parsed.flags


def test_hamburguer_picanha_prepared() -> None:
    parsed = parse_meat("Hambúrguer Bovino Maturatta Picanha 180g")
    assert not parsed.is_meat
    assert "prepared" in parsed.flags


# --- species peru is not frango ----------------------------------------------

def test_peito_de_peru_defumado_species_peru() -> None:
    parsed = parse_meat("PEITO DE PERU DEFUMADO SADIA KG")
    assert parsed.species == "peru"
    assert parsed.cut == "peito"
    assert parsed.species != "frango"


def test_salsicha_peru_species_peru() -> None:
    parsed = parse_meat("Salsicha Peru Sadia 500g")
    assert parsed.species == "peru"
    assert parsed.cut == "salsicha"


# --- convenience foods that carry a meat word do not hijack cut families ------

def test_pizza_de_lombo_non_meat() -> None:
    parsed = parse_meat("PIZZA SEARA LOMBO C/CATUPIRY 460GR")
    assert not parsed.is_meat


def test_macarrao_instantaneo_lombo_non_meat() -> None:
    parsed = parse_meat("Macarrão Instantâneo Nissin Lombo Com Limão 85g")
    assert not parsed.is_meat


def test_pate_peito_peru_non_meat() -> None:
    parsed = parse_meat("PATÊ PEITO PERU SEARA 100GR")
    assert not parsed.is_meat


def test_lasanha_peito_peru_non_meat() -> None:
    parsed = parse_meat("LASANHA SADIA PEITO PERU 600G")
    assert not parsed.is_meat


# --- doce de bananinha is not a beef cut -------------------------------------

def test_bananinha_doce_non_meat() -> None:
    parsed = parse_meat("Bananinha Cremosa Tradicional Oliveira 30g")
    assert not parsed.is_meat


def test_bananinha_bovina_real_cut() -> None:
    parsed = parse_meat("Bananinha Bovina Swift Congelada 1kg")
    assert parsed.cut == "bananinha"
    assert parsed.species == "bovino"
    assert parsed.is_meat


def test_peito_peru_soja_non_meat() -> None:
    parsed = parse_meat("PEITO DE PERU SOJA FATIADO 200G")
    assert not parsed.is_meat


def test_doce_salmao_non_meat() -> None:
    parsed = parse_meat("DOCE SALMÃO MARIA MOLE BANDEJA 150G")
    assert not parsed.is_meat


def test_coxinha_da_asa_continues_being_cut() -> None:
    parsed = parse_meat("Coxinha da Asa de Frango Congelada Aurora 1kg")
    assert parsed.cut == "coxinha_da_asa"
    assert parsed.is_meat


def test_coxinha_frita_tilapia_prepared() -> None:
    parsed = parse_meat("Coxinha Com Tilápia Brazilian Fish 400g")
    assert not parsed.is_meat


def test_filezinho_sassami_frango_maps_to_sassami() -> None:
    parsed = parse_meat("Filezinho de Frango Sassami Seara Congelado 1kg")
    assert parsed.cut == "sassami"
    assert parsed.species == "frango"


def test_hambuguer_misspelling_prepared() -> None:
    parsed = parse_meat("Hambúguer Perdigão Na Brasa Linguiça Suína 150g")
    assert not parsed.is_meat


def test_bolinhos_mandioca_carne_seca_non_meat() -> None:
    parsed = parse_meat("Bolinhos Mandioca Carne Seca Swift 300g")
    assert not parsed.is_meat


