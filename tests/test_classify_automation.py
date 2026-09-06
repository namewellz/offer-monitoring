from app.classification import automation as au


def _cand(pid, name, cats=None):
    return {
        "product_id": pid,
        "raw_name": name,
        "retailer": "atacadao",
        "raw_categories": cats or [],
    }


def test_bucket_by_department(monkeypatch):
    # departamento determinístico vem da taxonomia; aqui simulamos por categoria
    def fake_department(cats, name):
        first = (cats or [""])[0].lower()
        return {
            "mercearia": "Mercearia",
            "bebidas": "Bebidas",
            "acougue": "Açougue",
        }.get(first, None)

    monkeypatch.setattr(au, "canonical_department", fake_department)
    candidates = [
        _cand(1, "Arroz 5kg", ["mercearia"]),
        _cand(2, "Refrigerante 2L", ["bebidas"]),
        _cand(3, "Mamão Bandeja", []),
        _cand(4, "Picanha", ["acougue"]),
    ]
    buckets = au.bucket_by_department(candidates)
    assert set(buckets) == {"Mercearia", "Bebidas", "Açougue", "Outros"}
    assert [c["product_id"] for c in buckets["Mercearia"]] == [1]
    assert [c["product_id"] for c in buckets["Outros"]] == [3]


def test_skip_departments_constant():
    assert "Outros" in au._SKIP
    assert None in au._SKIP
