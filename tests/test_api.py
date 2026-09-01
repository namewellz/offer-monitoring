from app import main
from app.main import item_or_404


def test_item_or_404_returns_existing_item() -> None:
    value = object()
    assert item_or_404(value, "Thing") is value


def test_request_all_catalog_collections_enqueues_every_source(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "enqueue_catalog_collection",
        lambda retailer: f"job-{retailer}",
    )

    response = main.request_all_catalog_collections()

    assert response["total"] == len(main.CATALOG_COLLECTORS)
    assert {job["retailer"] for job in response["jobs"]} == set(main.CATALOG_COLLECTORS)
    assert all(job["job_id"].startswith("job-") for job in response["jobs"])


def test_catalog_collection_history_returns_recent_jobs(monkeypatch) -> None:
    jobs = [{"job_id": "job-1", "retailer": "savegnago", "status": "failed"}]
    monkeypatch.setattr(main, "recent_catalog_collection_jobs", lambda limit: jobs[:limit])

    assert main.catalog_collection_history(limit=10) == {"jobs": jobs}
