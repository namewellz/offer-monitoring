"""Helpers shared by the VTEX-based catalog collectors.

VTEX exposes the category tree as nested nodes; collectors walk it to build the
``fq=C:/<id>/<id>/`` filters used by
``/api/catalog_system/pub/products/search``. Both the legacy Atacadão VTEX
collector and the Savegnago collector need the same walk, so it lives here
instead of inside one of them.
"""
from __future__ import annotations

from typing import Any


def leaf_categories(
    nodes: list[dict[str, Any]], parent_ids: tuple[int, ...] = ()
) -> list[tuple[str, str]]:
    """Return ``(filter, name)`` for every leaf of the VTEX category tree."""
    leaves: list[tuple[str, str]] = []
    for node in nodes:
        path_ids = (*parent_ids, int(node["id"]))
        children = node.get("children") or []
        if children:
            leaves.extend(leaf_categories(children, path_ids))
        else:
            leaves.append((f"C:/{'/'.join(map(str, path_ids))}/", str(node.get("name") or node["id"])))
    return leaves


def top_categories(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return ``(filter, name)`` for the top level of the VTEX category tree."""
    return [(f"C:/{int(node['id'])}/", str(node.get("name") or node["id"])) for node in nodes]
