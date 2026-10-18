"""Attach an open item whose core already equals one A1 anchor."""

from __future__ import annotations

from collections.abc import Sequence

from app.canonical.refine import AnchorIndex, Item, Link, link_to


def ancora(open_items: Sequence[Item], anchors: AnchorIndex) -> list[Link]:
    links: list[Link] = []
    for item in open_items:
        anchor = anchors.lookup(item.brand_key, item.size, item.qty, item.core)
        if anchor is None:
            continue
        links.append(link_to(item, anchor, "ancora", item.core))
    return links
