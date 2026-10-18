"""Brand dictionary decisions and the review-queue panel."""

import pytest

from app.canonical.dictionary import normalize_action, selected_approvals
from app.enrichment.brands_dashboard import render_brands_page
from app.enrichment.canonical_queue import render_canonical_queue


def test_approve_uses_the_typed_name() -> None:
    action = normalize_action({"action": "approve", "name": "Fest Lar"})
    assert action["key"] == "festlar"
    assert action["action"] == "approve"


def test_alias_to_the_same_brand_is_an_approval() -> None:
    action = normalize_action(
        {"action": "alias", "key": "festlar", "name": "Fest Lar", "target": "Fest Lar"}
    )
    assert action["action"] == "approve"
    assert action["key"] == "festlar"


def test_alias_points_at_another_brand() -> None:
    action = normalize_action(
        {"action": "alias", "key": "tiroj", "name": "Tiro J", "target": "Tirolez"}
    )
    assert action == {
        "action": "alias",
        "key": "tiroj",
        "name": "Tiro J",
        "target_name": "Tirolez",
        "target_key": "tirolez",
    }


def test_selected_approvals_keep_each_distinct_brand() -> None:
    items = selected_approvals(
        {
            "action": "approve_selected",
            "items": [
                {"key": "festlar", "name": "Fest Lar"},
                {"key": "festlar", "name": "Fest Lar"},
                {"name": "Sadia"},
            ],
        }
    )
    assert [item["key"] for item in items] == ["festlar", "sadia"]
    assert all(item["action"] == "approve" for item in items)


def test_selected_approvals_reject_an_empty_list() -> None:
    with pytest.raises(ValueError, match="marque ao menos uma marca"):
        selected_approvals({"action": "approve_selected", "items": []})


def test_blank_or_placeholder_brand_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalize_action({"action": "approve", "name": "!!!"})
    with pytest.raises(ValueError):
        normalize_action({"action": "block", "key": "semmarca", "name": "sem marca"})
    with pytest.raises(ValueError):
        normalize_action({"action": "alias", "name": "Ypê", "target": ""})


def test_brands_page_lists_a_candidate_and_escapes_the_name() -> None:
    html = render_brands_page(
        {
            "q": "",
            "inferred_total": 2,
            "shown": 1,
            "decisions": 0,
            "normalizer_version": "canon-3.0",
            "rows": [
                {
                    "key": "festlar",
                    "name": "Fest <Lar>",
                    "items": 32,
                    "retailers": 1,
                    "origin": "inferred",
                    "sample": "Balão Fest Lar",
                    "status": "candidate",
                    "status_label": "candidata",
                }
            ],
        }
    )
    assert "Fest &lt;Lar&gt;" in html
    assert "Aprovar selecionados" in html
    assert "id='pick-all'" in html
    assert "data-name='Fest &lt;Lar&gt;'" in html
    assert "Bloquear" in html
    assert "Vincular" in html
    assert "ainda não lê essas tabelas" in html


def test_review_queue_links_the_group_and_lists_a_product() -> None:
    html = render_canonical_queue(
        {
            "department": "Açougue",
            "base": "/catalog/butcher-review",
            "counts": {"B1": 12, "B2": 0, "B3": 3, "B4": 1, "R": 4},
            "group": "B1",
            "label": "Marca só inferida do título",
            "total": 12,
            "rows": [
                {
                    "name": "Picanha Friboi",
                    "brand": "Friboi",
                    "size": "1kg",
                    "pack": None,
                    "retailer": "Assaí",
                }
            ],
        }
    )
    assert "Fila canônica" in html
    assert "B1 · 12" in html
    assert "fila=B1" in html
    assert "Picanha Friboi" in html
    assert "Mostrando 1 de 12." in html
