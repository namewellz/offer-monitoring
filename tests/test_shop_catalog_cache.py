"""Shop catalog / butcher caches: single-flight, stale-while-revalidate, per-filter keys."""

from __future__ import annotations

import threading
import time

from sqlalchemy.dialects import postgresql

from app.catalog.v2.read import _current_listings_query
from app.enrichment import butcher, shop_catalog
from app.shopping.pages import render_builder
from app.stores import CURRENT_FILTER, StoreFilter


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def rollback(self):
        pass


def _patch_session(monkeypatch):
    import app.db.session as session_mod

    monkeypatch.setattr(session_mod, "SessionLocal", lambda: _FakeSession())


def _line(name: str) -> dict:
    return {
        "department": "Mercearia",
        "category": name,
        "form": "un",
        "label": "un",
        "unit": "un",
        "sources": {"x": {"price": 1.0, "store": "S", "sample": name}},
    }


def _reset(monkeypatch):
    monkeypatch.setattr(shop_catalog, "_CACHE", {})
    monkeypatch.setattr(shop_catalog, "_REFRESHING", set())
    monkeypatch.setattr(shop_catalog, "canonical_name", lambda *a, **k: _Canon())


class _Canon:
    generic = specific = ""
    brand = size = None


def _wait_background():
    for _ in range(100):
        if not shop_catalog._REFRESHING:
            return
        time.sleep(0.02)
    raise AssertionError("background refresh did not finish")


def test_concurrent_cold_requests_compute_once(monkeypatch):
    _reset(monkeypatch)
    _patch_session(monkeypatch)
    calls = []

    def slow(db):
        calls.append(1)
        time.sleep(0.2)
        return [_line("Arroz")]

    monkeypatch.setattr(shop_catalog, "_compute_lines", slow)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(shop_catalog.catalog_search_index()))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert all(r and "Mercearia|Arroz|un" in r for r in results)


def test_non_blocking_cold_returns_none_and_warms_in_background(monkeypatch):
    _reset(monkeypatch)
    _patch_session(monkeypatch)
    done = threading.Event()

    def compute(db):
        done.set()
        return [_line("Feijao")]

    monkeypatch.setattr(shop_catalog, "_compute_lines", compute)
    assert shop_catalog.catalog_search_index(block=False) is None
    assert done.wait(2)
    _wait_background()
    assert "Mercearia|Feijao|un" in shop_catalog.catalog_search_index(block=False)


def test_stale_entry_is_served_while_refreshing(monkeypatch):
    _reset(monkeypatch)
    _patch_session(monkeypatch)
    release = threading.Event()

    def compute(db):
        release.wait(2)
        return [_line("Novo")]

    monkeypatch.setattr(shop_catalog, "_compute_lines", compute)
    key = CURRENT_FILTER.get().key
    old = shop_catalog._store(key, [_line("Velho")])
    old["ts"] -= shop_catalog._TTL + 1
    started = time.monotonic()
    index = shop_catalog.catalog_search_index()
    assert time.monotonic() - started < 0.5  # não esperou o recálculo
    assert "Mercearia|Velho|un" in index
    release.set()
    _wait_background()
    assert "Mercearia|Novo|un" in shop_catalog.catalog_search_index()


def test_cache_is_keyed_by_store_filter(monkeypatch):
    _reset(monkeypatch)
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        shop_catalog,
        "_compute_lines",
        lambda db: [_line("rede" if CURRENT_FILTER.get().rede else "default")],
    )
    default = shop_catalog.catalog_search_index()
    token = CURRENT_FILTER.set(StoreFilter(rede=("dalben",)))
    try:
        filtered = shop_catalog.catalog_search_index()
    finally:
        CURRENT_FILTER.reset(token)
    assert "Mercearia|default|un" in default
    assert "Mercearia|default|un" in shop_catalog.catalog_search_index()
    assert "Mercearia|rede|un" in filtered
    assert len(shop_catalog._CACHE) == 2


def test_butcher_stale_with_rows_recomputes_from_rows(monkeypatch):
    monkeypatch.setattr(butcher, "_CACHE", {})
    seen = {}

    def compute(db, use_llm, rows=None, release=False):
        seen["rows"] = rows
        seen["release"] = release
        return 1, [{"category": "Picanha", "form": "peca_kg", "sources": {}}], {}

    monkeypatch.setattr(butcher, "_compute", compute)
    rows = [("r",)]
    out = butcher.butcher_comparison(object(), limit=10, rows=rows, release=True)
    assert seen == {"rows": rows, "release": True}
    assert out["total_items"] == 1


def test_current_listings_optional_filters_compile():
    base = str(_current_listings_query().compile(dialect=postgresql.dialect()))
    narrowed = str(
        _current_listings_query(fresh_only=True, accepted_only=True).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "last_confirmed_at >=" not in base
    assert "llm_classifications" not in base
    assert "price_periods_1.last_confirmed_at >=" in narrowed
    assert "llm_classifications.decision" in narrowed


def test_builder_pending_flag_renders_without_catalog():
    items = [
        {
            "id": 7,
            "department": "Mercearia",
            "category": "Arroz",
            "form": "un",
            "retailer": "dalben",
            "qty": 2,
            "note": "x",
        }
    ]
    html = render_builder("L", 4, {}, items, catalog_pending=True)
    assert "const CATALOG_PENDING = true;" in html
    assert 'data-retailer="dalben"' in html
    assert "@@" not in html
    assert "const CATALOG_PENDING = false;" in render_builder("L", 4, {}, [])
