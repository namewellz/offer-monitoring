from app.enrichment.canonical_name import CanonicalName, canonical_name, search_terms


def test_beer_brand_specific_and_generic() -> None:
    result = canonical_name(
        "Cerveja Heineken 350ml", brand="Heineken", department="Bebidas"
    )
    assert result.generic == "Cerveja"
    assert result.specific == "Cerveja Heineken 350ml"
    assert result.brand == "Heineken"
    assert result.size == "350ml"
    assert result.brand_relevant is True
    assert result.class_name == "Cerveja"


def test_rice_brand_detected_from_name() -> None:
    result = canonical_name("Arroz Tio João 5kg", department="Mercearia")
    assert result.generic == "Arroz"
    assert result.specific == "Arroz Tio João 5kg"
    assert result.brand == "Tio João"
    assert result.size == "5kg"


def test_coffee_brand_and_size() -> None:
    result = canonical_name(
        "Café Pilão Tradicional 500g", brand="Pilão", department="Mercearia"
    )
    assert result.generic == "Café"
    assert result.specific == "Café Pilão 500g"
    assert result.size == "500g"


def test_commodity_brand_irrelevant() -> None:
    result = canonical_name("Sal Refinado 1kg", department="Mercearia")
    assert result.generic == "Sal"
    assert result.specific == "Sal"
    assert result.brand_relevant is False


def test_hortifruti_uses_produce_identity() -> None:
    result = canonical_name("Maçã Fuji", department="Hortifruti")
    assert result.generic == "Maçã"
    assert result.specific == "Maçã Fuji"
    assert result.brand_relevant is False

    banana = canonical_name("Banana Prata 1kg", department="Hortifruti")
    assert banana.generic == "Banana"
    assert banana.specific == "Banana Prata"


def test_butcher_brand_never_in_identity() -> None:
    result = canonical_name("Picanha Friboi 1kg", department="Açougue")
    assert result.generic == result.specific
    assert "Friboi" not in result.generic
    assert result.brand_relevant is False


def test_unknown_class_falls_back_to_cleaned_base() -> None:
    result = canonical_name("Fita Crepe 50m", department="Bazar e Utilidades")
    assert result.generic == result.specific
    assert result.generic


def test_water_de_coco_not_water_mineral() -> None:
    result = canonical_name("Água de Coco Kero Coco 1l", brand="Kero Coco", department="Bebidas")
    assert result.generic == "Água de Coco"


def test_bread_uses_brand_when_present() -> None:
    result = canonical_name(
        "Pão de Forma Pullman 500g", brand="Pullman", department="Padaria"
    )
    assert result.generic == "Pão de Forma"
    assert result.specific == "Pão de Forma Pullman 500g"
    assert result.brand == "Pullman"
    assert result.brand_relevant is True


def test_bread_brand_detected_from_name_without_field() -> None:
    result = canonical_name("Pão de Forma Wickbold 500g", department="Padaria")
    assert result.specific == "Pão de Forma Wickbold 500g"
    assert result.brand == "Wickbold"


def test_class_detected_from_categories_when_name_is_short() -> None:
    result = canonical_name(
        "Pullman 500g",
        brand="Pullman",
        department="Padaria",
        categories=["Padaria", "Pães", "Pão de Forma"],
    )
    assert result.generic == "Pão de Forma"
    assert result.specific == "Pão de Forma Pullman 500g"


def test_search_terms_cover_generic_specific_brand() -> None:
    result = canonical_name(
        "Cerveja Heineken 350ml", brand="Heineken", department="Bebidas"
    )
    terms = search_terms(result, raw="Cerveja Heineken Lata 350ml")
    joined = " | ".join(terms).casefold()
    assert "cerveja" in joined
    assert "heineken" in joined
    assert "350ml" in joined
    assert "lata" in joined
