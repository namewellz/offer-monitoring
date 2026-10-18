"""Stage refinements over items the canon left open.

A1 rows are anchors. A2 rows may attach to one anchor. Nothing here writes the
canon columns. ``save_refinements`` only adds rows to ``canonical_refinements``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

REFINER_VERSION = "refino-1"


@dataclass(frozen=True)
class Item:
    id: int
    retailer: str
    brand_key: str
    size: str
    qty: int
    core: str
    group: str
    gtin: str = ""


@dataclass(frozen=True)
class Anchor:
    match_key: str
    version_id: int
    brand_key: str
    size: str
    qty: int
    core: str


@dataclass(frozen=True)
class Link:
    item_id: int
    stage: str
    anchor_match_key: str
    anchor_version_id: int
    core_before: str
    core_after: str


@dataclass(frozen=True)
class StageReport:
    stage: str
    entered: int
    closed: int
    still_open: int


@dataclass(frozen=True)
class RefineResult:
    links: tuple[Link, ...]
    reports: tuple[StageReport, ...]
    open_ids: tuple[int, ...]


class AnchorIndex:
    """One anchor per brand, size, quantity and core. The version id is the smallest."""

    def __init__(self, items: Sequence[Item]) -> None:
        grouped: dict[tuple[str, str, int, str], list[Item]] = defaultdict(list)
        for item in items:
            if item.group != "A1" or not item.brand_key or not item.size or not item.core:
                continue
            grouped[(item.brand_key, item.size, item.qty, item.core)].append(item)
        self._by_key: dict[tuple[str, str, int, str], Anchor] = {}
        for key, rows in grouped.items():
            brand, size, qty, core = key
            representative = min(rows, key=lambda row: row.id)
            self._by_key[key] = Anchor(
                match_key=f"{brand}|{core}|{size}|{qty}",
                version_id=representative.id,
                brand_key=brand,
                size=size,
                qty=qty,
                core=core,
            )

    def lookup(self, brand_key: str, size: str, qty: int, core: str) -> Anchor | None:
        return self._by_key.get((brand_key, size, qty, core))


def link_to(item: Item, anchor: Anchor, stage: str, core_after: str) -> Link:
    return Link(
        item_id=item.id,
        stage=stage,
        anchor_match_key=anchor.match_key,
        anchor_version_id=anchor.version_id,
        core_before=item.core,
        core_after=core_after,
    )


def _eligible(item: Item) -> bool:
    return bool(item.group == "A2" and item.brand_key and item.size and item.core)


def _accept(open_items: Sequence[Item], proposed: Sequence[Link]) -> list[Link]:
    pending = {item.id for item in open_items}
    by_item: dict[int, list[Link]] = defaultdict(list)
    for link in proposed:
        if link.item_id in pending:
            by_item[link.item_id].append(link)
    accepted: list[Link] = []
    for links in by_item.values():
        keys = {link.anchor_match_key for link in links}
        if len(keys) == 1:
            accepted.append(links[0])
    return accepted


def run(items: Sequence[Item]) -> RefineResult:
    """Close A2 items stage by stage. A1 items stay anchors and are not revisited."""
    from app.canonical.stages import STAGES

    anchors = AnchorIndex(items)
    open_items = [item for item in items if _eligible(item)]
    links: list[Link] = []
    reports: list[StageReport] = []
    for stage in STAGES:
        entered = len(open_items)
        accepted = _accept(open_items, stage(open_items, anchors))
        closed_ids = {link.item_id for link in accepted}
        open_items = [item for item in open_items if item.id not in closed_ids]
        links.extend(accepted)
        reports.append(
            StageReport(stage.__name__, entered, len(accepted), len(open_items))
        )
    return RefineResult(tuple(links), tuple(reports), tuple(item.id for item in open_items))


def save_refinements(db, links: Sequence[Link], *, refiner_version: str = REFINER_VERSION) -> int:
    """Add one refinement row per link. Does not commit and does not touch canon rows."""
    from app.db.models_v2 import CanonicalRefinement

    for link in links:
        db.add(
            CanonicalRefinement(
                normalized_product_version_id=link.item_id,
                anchor_match_key=link.anchor_match_key,
                anchor_version_id=link.anchor_version_id,
                stage=link.stage,
                evidence={"core_before": link.core_before, "core_after": link.core_after},
                refiner_version=refiner_version,
            )
        )
    return len(links)
