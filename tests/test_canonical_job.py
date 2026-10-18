"""Post-collection canonical job: what gets queued, and what gets written."""

from types import SimpleNamespace

from app.canonical.incremental import rows_to_insert
from app.canonical.stats import format_pct
from app.catalog.v2.hashing import digest, source_product_state
from app.core.config import Settings
from app.jobs import tasks


def _item(version_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=version_id)


def test_canonical_flag_defaults_off() -> None:
    assert Settings.model_fields["canonical_enabled"].default is False


def test_only_pending_versions_are_inserted() -> None:
    items = [_item(1), _item(2), _item(3)]
    assert [item.id for item in rows_to_insert(items, {2})] == [2]


def test_price_and_image_do_not_change_the_product_hash() -> None:
    state = source_product_state(
        name="Leite Integral 1L",
        brand="Italac",
        gtin="7891000100103",
        categories=["Laticínios"],
        measure="1L",
    )
    assert "image" not in state
    assert "price" not in state
    renamed = source_product_state(
        name="Leite Integral Desnatado 1L",
        brand="Italac",
        gtin="7891000100103",
        categories=["Laticínios"],
        measure="1L",
    )
    assert digest(state) != digest(renamed)


def test_failed_collection_enqueues_nothing(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(canonical_enabled=True))
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_normalize_new",
        lambda slug: calls.append(f"normalize:{slug}"),
    )
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_classify_new",
        lambda retailer_slug=None: calls.append(f"classify:{retailer_slug}"),
    )
    tasks.enqueue_post_collection("goodbom", "FAILED")
    assert calls == []


def test_success_queues_normalize_before_classify_when_enabled(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(canonical_enabled=True))
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_normalize_new",
        lambda slug: calls.append(f"normalize:{slug}") or "n",
    )
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_classify_new",
        lambda retailer_slug=None: calls.append(f"classify:{retailer_slug}") or "c",
    )
    tasks.enqueue_post_collection("goodbom", "PARTIAL_SUCCESS")
    assert calls == ["normalize:goodbom", "classify:goodbom"]


def test_normalize_error_still_queues_classification(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(canonical_enabled=True))

    def explode(slug: str) -> str:
        calls.append(f"normalize:{slug}")
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.jobs.queue.enqueue_normalize_new", explode)
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_classify_new",
        lambda retailer_slug=None: calls.append(f"classify:{retailer_slug}") or "c",
    )
    tasks.enqueue_post_collection("goodbom", "SUCCESS")
    assert calls == ["normalize:goodbom", "classify:goodbom"]


def test_disabled_flag_queues_only_classification(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(canonical_enabled=False))
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_normalize_new",
        lambda slug: calls.append(f"normalize:{slug}"),
    )
    monkeypatch.setattr(
        "app.jobs.queue.enqueue_classify_new",
        lambda retailer_slug=None: calls.append(f"classify:{retailer_slug}") or "c",
    )
    tasks.enqueue_post_collection("goodbom", "SUCCESS")
    assert calls == ["classify:goodbom"]


def test_job_returns_before_redis_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(canonical_enabled=False))
    opened: list[str] = []
    monkeypatch.setattr(tasks, "SessionLocal", lambda: opened.append("db"))
    monkeypatch.setattr(tasks, "_locked", lambda name: opened.append(name))
    result = tasks.run_normalize_new("goodbom")
    assert result == {"skipped": True, "reason": "canonical_disabled", "retailer": "goodbom"}
    assert opened == []


def test_coverage_percent_uses_comma() -> None:
    assert format_pct(202179, 228892) == "88,3%"
    assert format_pct(0, 0) == "—"
