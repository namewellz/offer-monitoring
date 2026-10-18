"""Fold a trailing plural s, then attach only when one anchor matches."""

from __future__ import annotations

from collections.abc import Sequence

from app.canonical.refine import AnchorIndex, Item, Link, link_to


def _plural_cores(core: str) -> list[str]:
    tokens = core.split()
    indexes = [
        index
        for index, token in enumerate(tokens)
        if len(token) >= 5 and token.endswith("s") and not token.endswith("ss")
    ]
    if not indexes:
        return []
    found: list[str] = []

    def add(updated: list[str]) -> None:
        text = " ".join(sorted(set(updated)))
        if text and text != core and text not in found:
            found.append(text)

    for index in indexes:
        updated = tokens.copy()
        updated[index] = updated[index][:-1]
        add(updated)
    updated = tokens.copy()
    for index in indexes:
        updated[index] = updated[index][:-1]
    add(updated)
    return found


def plural(open_items: Sequence[Item], anchors: AnchorIndex) -> list[Link]:
    links: list[Link] = []
    for item in open_items:
        hits = []
        for core in _plural_cores(item.core):
            anchor = anchors.lookup(item.brand_key, item.size, item.qty, core)
            if anchor is not None and anchor.match_key not in {hit.match_key for hit in hits}:
                hits.append(anchor)
        if len(hits) != 1:
            continue
        links.append(link_to(item, hits[0], "plural", hits[0].core))
    return links
