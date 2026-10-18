"""Spelling variants of the same butcher cut share one shopping-list line."""

from app.classification.canonical import equivalent_cut_category


def test_coxa_sobrecoxa_spellings_are_one_cut():
    same = "Coxa/Sobrecoxa de Frango"
    assert equivalent_cut_category("Coxa e Sobrecoxa de Frango") == same
    assert equivalent_cut_category("Coxa/Sobrecoxa de Frango") == same
    assert equivalent_cut_category("Coxa com Sobrecoxa de Frango") == same
    assert equivalent_cut_category("Coxa/Sobrecoxa") == same


def test_coxa_and_sobrecoxa_alone_stay_separate():
    assert equivalent_cut_category("Coxa de Frango") == "Coxa de Frango"
    assert equivalent_cut_category("Sobrecoxa de Frango") == "Sobrecoxa de Frango"
    assert equivalent_cut_category("Sobrecoxa") == "Sobrecoxa"
    assert equivalent_cut_category("Coxa Desossada") == "Coxa Desossada"
    assert equivalent_cut_category("Coxa de Frango Temperada") == "Coxa de Frango Temperada"
    assert equivalent_cut_category("Coxa de Frango Passarinho") == "Coxa de Frango Passarinho"


def test_bone_and_seasoning_stay_their_own_lines():
    boneless = "Coxa/Sobrecoxa de Frango Sem Osso"
    assert equivalent_cut_category("Coxa e Sobrecoxa de Frango Sem Osso") == boneless
    assert equivalent_cut_category("Coxa e Sobrecoxa de Frango sem Osso") == boneless
    assert equivalent_cut_category("Coxa/Sobrecoxa de Frango Sem Osso") == boneless
    assert equivalent_cut_category("Coxa/Sobrecoxa sem Osso") == boneless
    seasoned = "Coxa/Sobrecoxa de Frango Temperada"
    assert equivalent_cut_category("Coxa e Sobrecoxa de Frango Temperada") == seasoned
    assert equivalent_cut_category("Coxa/Sobrecoxa de Frango Temperada") == seasoned
    both = "Coxa/Sobrecoxa de Frango Sem Osso Temperada"
    assert equivalent_cut_category("Coxa e Sobrecoxa de Frango sem Osso Temperada") == both


def test_other_birds_and_other_cuts_stay_separate():
    assert equivalent_cut_category("Coxa e Sobrecoxa de Chester") == "Coxa/Sobrecoxa de Chester"
    assert equivalent_cut_category("Coxa e Sobrecoxa de Pato") == "Coxa/Sobrecoxa de Pato"
    assert (
        equivalent_cut_category("Filé de Coxa e Sobrecoxa de Frango")
        == "Filé de Coxa e Sobrecoxa de Frango"
    )
    assert (
        equivalent_cut_category("Espetinho de Coxa e Sobrecoxa")
        == "Espetinho de Coxa e Sobrecoxa"
    )
