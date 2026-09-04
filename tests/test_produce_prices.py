from app.enrichment.produce_prices import _aggregate, _per_kg


def _entry(pid, raw, price, retailer="atacadao", retailer_name="Atacadão", store="Loja A"):
    return {
        "pid": pid,
        "price": price,
        "raw": raw,
        "retailer": retailer,
        "retailer_name": retailer_name,
        "store": store,
    }


def test_presentations_of_same_product_group_by_identity():
    entries = [
        _entry(1, "Maçã Fuji Kg", 9.98),
        _entry(2, "Maçã Fuji Bandeja 600g", 6.0),
        _entry(3, "MAÇÃ FUJI 1KG", 9.5, retailer="tenda", retailer_name="Tenda", store="Loja B"),
    ]
    identities, unmodeled = _aggregate(entries)
    assert unmodeled == 0
    products = [it["product"] for it in identities]
    assert products == ["Maçã Fuji"], products
    item = identities[0]
    assert item["products"] == 3
    # per kg: 9.98 ; 6.00/0.6 = 10.0 ; 9.5 -> best across retailers is Tenda 9.5
    assert item["best"]["slug"] == "tenda"
    assert round(item["best"]["per_kg"], 2) == 9.5


def test_retailer_keeps_cheapest_presentation():
    entries = [
        _entry(1, "Maçã Fuji Kg", 12.0, retailer="assai"),
        _entry(2, "Maçã Fuji Bandeja 600g", 5.4, retailer="assai"),  # 9.0/kg
    ]
    identities, _ = _aggregate(entries)
    item = identities[0]
    assert round(item["best"]["per_kg"], 2) == 9.0
    assert item["best"]["presentation"] == "bandeja 600 g"


def test_generic_apple_is_separate_from_variety():
    entries = [
        _entry(1, "Maçã Fuji Kg", 9.98),
        _entry(2, "MAÇÃ IMPORTADA VERMELHA KG", 8.0),
        _entry(3, "Maçã Argentina Bandeja 720g", 6.48),  # 9.0/kg
    ]
    identities, _ = _aggregate(entries)
    products = sorted(it["product"] for it in identities)
    assert products == ["Maçã", "Maçã Fuji"], products


def test_banana_maca_not_grouped_as_apple():
    entries = [
        _entry(1, "Maçã Fuji Kg", 9.98),
        _entry(2, "Banana Maçã Kg", 8.0),
    ]
    identities, _ = _aggregate(entries)
    products = sorted(it["product"] for it in identities)
    assert products == ["Banana Maçã", "Maçã Fuji"], products


def test_unit_only_goes_to_unit_bucket():
    entries = [
        _entry(1, "Maçã Fuji Unidade", 3.5, retailer="assai", store="Loja C"),
        _entry(2, "Maçã Fuji Kg", 9.98, retailer="atacadao"),
    ]
    identities, _ = _aggregate(entries)
    item = identities[0]
    # kg bucket only from atacadao; assai per unidade kept in unit_only
    assert [r["slug"] for r in item["retailers"]] == ["atacadao"]
    assert [r["slug"] for r in item["unit_only"]] == ["assai"]
    assert item["best"]["slug"] == "atacadao"


def test_unmodeled_entries_are_counted_not_grouped():
    entries = [
        _entry(1, "Maçã Fuji Kg", 9.98),
        _entry(2, "Arroz 5kg", 21.0),
    ]
    identities, unmodeled = _aggregate(entries)
    assert unmodeled == 1
    assert [it["product"] for it in identities] == ["Maçã Fuji"]


def test_per_kg_normalization():
    assert _per_kg(6.0, "Bandeja", 600.0) == 10.0  # 6.00 / 0.6 kg
    assert _per_kg(9.98, "Kg", None) == 9.98        # implicit 1 kg
    assert _per_kg(3.5, "Unidade", None) is None    # cannot normalize
    assert _per_kg(24.99, "", 1000.0) == 24.99
