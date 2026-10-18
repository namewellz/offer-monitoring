"""Drop tokens that are not the product, then attach to one anchor."""

from __future__ import annotations

from collections.abc import Sequence

from app.canonical.refine import AnchorIndex, Item, Link, link_to

NOISE = frozenset({"barcode", "multipack", "emb"})


def _without_noise(core: str) -> str:
    tokens = [token for token in core.split() if token not in NOISE]
    return " ".join(tokens)


def ruido(open_items: Sequence[Item], anchors: AnchorIndex) -> list[Link]:
    links: list[Link] = []
    for item in open_items:
        core = _without_noise(item.core)
        if not core or core == item.core:
            continue
        anchor = anchors.lookup(item.brand_key, item.size, item.qty, core)
        if anchor is None:
            continue
        links.append(link_to(item, anchor, "ruido", core))
    return links
