"""Replace a whole token that has one destination, then attach to one anchor."""

from __future__ import annotations

from collections.abc import Sequence

from app.canonical.refine import AnchorIndex, Item, Link, link_to

# Words with more than one expansion in the corpus stay out: choc, cond, masc, hid.
ABBREV = {
    "ling": "linguica",
    "refrig": "refrigerante",
    "ceb": "cebola",
}


def _expanded(core: str) -> str:
    tokens = [ABBREV.get(token, token) for token in core.split()]
    return " ".join(sorted(set(tokens)))


def abrev(open_items: Sequence[Item], anchors: AnchorIndex) -> list[Link]:
    links: list[Link] = []
    for item in open_items:
        core = _expanded(item.core)
        if core == item.core:
            continue
        anchor = anchors.lookup(item.brand_key, item.size, item.qty, core)
        if anchor is None:
            continue
        links.append(link_to(item, anchor, "abrev", core))
    return links
