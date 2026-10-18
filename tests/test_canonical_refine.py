"""Stage refinements stay off the canon columns and only link an open A2 to one A1."""

from app.canonical.refine import Item, run, save_refinements
from app.canonical.stages import STAGES


def item(**kwargs) -> Item:
    base = dict(
        id=1,
        retailer="assai",
        brand_key="sadia",
        size="1000g",
        qty=0,
        core="linguica",
        group="A2",
        gtin="",
    )
    base.update(kwargs)
    return Item(**base)


def test_stage_order_is_the_pipeline():
    assert [stage.__name__ for stage in STAGES] == ["ancora", "plural", "abrev", "ruido"]


def test_ancora_joins_an_open_item_to_the_same_core():
    anchor = item(id=5, retailer="atacadao", group="A1", core="linguica")
    other = item(id=9, retailer="tenda", group="A1", core="linguica")
    open_item = item(id=3, retailer="goodbom", core="linguica")
    result = run([other, open_item, anchor])
    assert len(result.links) == 1
    link = result.links[0]
    assert link.stage == "ancora"
    assert link.item_id == 3
    assert link.anchor_version_id == 5
    assert link.anchor_match_key == "sadia|linguica|1000g|0"
    assert result.open_ids == ()


def test_two_open_items_without_an_anchor_stay_open():
    result = run(
        [
            item(id=1, retailer="assai", core="linguica"),
            item(id=2, retailer="goodbom", core="linguica"),
        ]
    )
    assert result.links == ()
    assert result.open_ids == (1, 2)


def test_plural_joins_roupas_to_roupa_and_abstains_when_two_anchors_match():
    closed = run(
        [
            item(id=1, brand_key="brilhante", size="800g", group="A1", core="roupa"),
            item(id=2, brand_key="brilhante", size="800g", core="roupas"),
        ]
    )
    assert [(link.stage, link.core_after) for link in closed.links] == [("plural", "roupa")]

    ambiguous = run(
        [
            item(id=1, group="A1", core="finas roupa"),
            item(id=2, group="A1", core="fina roupas"),
            item(id=3, core="finas roupas"),
        ]
    )
    assert ambiguous.links == ()
    assert ambiguous.open_ids == (3,)


def test_abbreviation_map_is_closed():
    expanded = run(
        [
            item(id=1, brand_key="sukita", size="2000ml", group="A1", core="laranja refrigerante"),
            item(id=2, brand_key="sukita", size="2000ml", core="laranja refrig"),
        ]
    )
    assert [(link.stage, link.core_after) for link in expanded.links] == [
        ("abrev", "laranja refrigerante")
    ]

    left_out = run(
        [
            item(id=1, brand_key="bauducco", size="27g", group="A1", core="chocolate"),
            item(id=2, brand_key="bauducco", size="27g", core="choc"),
            item(id=3, brand_key="above", size="325ml", group="A1", core="condicionador"),
            item(id=4, brand_key="above", size="325ml", core="cond"),
        ]
    )
    assert left_out.links == ()
    assert left_out.open_ids == (2, 4)


def test_noise_token_is_removed_and_a_real_word_stays():
    cleaned = run(
        [
            item(id=1, brand_key="cocacola", size="350ml", group="A1", core="refrigerante"),
            item(id=2, brand_key="cocacola", size="350ml", core="barcode refrigerante"),
        ]
    )
    assert [(link.stage, link.core_after) for link in cleaned.links] == [("ruido", "refrigerante")]

    kept = run(
        [
            item(id=1, brand_key="cocacola", size="350ml", group="A1", core="refrigerante"),
            item(id=2, brand_key="cocacola", size="350ml", core="embalagem refrigerante"),
        ]
    )
    assert kept.links == ()


def test_an_item_closed_by_ancora_does_not_change_stage():
    result = run(
        [
            item(id=1, group="A1", core="roupa"),
            item(id=2, core="roupa"),
        ]
    )
    assert [link.stage for link in result.links] == ["ancora"]
    assert [report.stage for report in result.reports] == [
        "ancora",
        "plural",
        "abrev",
        "ruido",
    ]
    assert result.reports[1].entered == 0


def test_groups_outside_a2_are_ignored():
    result = run(
        [
            item(id=1, group="A1", core="roupa"),
            item(id=2, group="B1", core="roupas"),
            item(id=3, group="A2", size="", core="roupas"),
        ]
    )
    assert result.links == ()
    assert result.open_ids == ()


def test_save_adds_a_row_and_leaves_the_anchor_untouched():
    anchor = item(id=1, group="A1", core="linguica")
    open_item = item(id=2, core="linguica")
    before = anchor
    result = run([anchor, open_item])

    class Session:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

    session = Session()
    assert save_refinements(session, result.links) == 1
    row = session.added[0]
    assert row.normalized_product_version_id == 2
    assert row.anchor_version_id == 1
    assert row.anchor_match_key == "sadia|linguica|1000g|0"
    assert row.stage == "ancora"
    assert row.evidence == {"core_before": "linguica", "core_after": "linguica"}
    assert row.refiner_version == "refino-1"
    assert anchor == before
    assert anchor.group == "A1"
