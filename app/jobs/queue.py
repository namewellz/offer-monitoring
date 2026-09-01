from uuid import UUID

from redis import Redis
from rq import Queue
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from app.core.config import get_settings


def get_queue() -> Queue:
    return Queue("flyers", connection=Redis.from_url(get_settings().redis_url))


def enqueue_extraction(flyer_id: UUID) -> str:
    return get_queue().enqueue("app.jobs.tasks.run_extraction", str(flyer_id), job_timeout="15m").id


def enqueue_discovery(source_id: UUID) -> str:
    return get_queue().enqueue("app.jobs.tasks.run_discovery", str(source_id), job_timeout="10m").id


def enqueue_catalog_collection(retailer_slug: str) -> str:
    queue = get_queue()
    connection = queue.connection
    key = f"catalog:queued:{retailer_slug}"
    with connection.lock(f"{key}:lock", timeout=10, blocking_timeout=3):
        existing_id = connection.get(key)
        if existing_id:
            existing_id = existing_id.decode() if isinstance(existing_id, bytes) else existing_id
            existing = queue.fetch_job(existing_id)
            if existing is not None:
                status = existing.get_status(refresh=True)
                status = status.value if hasattr(status, "value") else str(status)
                if status in {"queued", "started", "deferred", "scheduled"}:
                    return existing.id
            connection.delete(key)
        job = queue.enqueue(
            "app.jobs.tasks.run_catalog_collection",
            retailer_slug,
            job_timeout="30m",
            result_ttl=86400,
            failure_ttl=86400,
        )
        connection.set(key, job.id, ex=7200)
        return job.id


def _catalog_job_error(exc_info: str | None) -> str | None:
    if not exc_info:
        return None
    lines = [line.strip() for line in exc_info.splitlines() if line.strip()]
    useful = [line for line in lines if not line.startswith("For more information check:")]
    return useful[-1] if useful else lines[-1] if lines else None


def _catalog_job_payload(job) -> dict:
    status = job.get_status(refresh=True)
    status = status.value if hasattr(status, "value") else str(status)
    result = job.result if status == "finished" else None
    return {
        "job_id": job.id,
        "status": status,
        "retailer": job.args[0] if job.args else None,
        "result": result,
        "outcome": result.get("status") if isinstance(result, dict) else None,
        "warnings": result.get("errors", []) if isinstance(result, dict) else [],
        "error": _catalog_job_error(job.exc_info) if status == "failed" else None,
        "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
    }


def catalog_collection_job(job_id: str) -> dict | None:
    job = get_queue().fetch_job(job_id)
    if job is None:
        return None
    return _catalog_job_payload(job)


def recent_catalog_collection_jobs(limit: int = 20) -> list[dict]:
    queue = get_queue()
    job_ids = list(queue.get_job_ids())
    for registry_type in (
        StartedJobRegistry,
        DeferredJobRegistry,
        ScheduledJobRegistry,
        FinishedJobRegistry,
        FailedJobRegistry,
    ):
        job_ids.extend(registry_type(queue=queue).get_job_ids())

    jobs = []
    for job_id in dict.fromkeys(job_ids):
        job = queue.fetch_job(job_id)
        if job is not None and job.func_name == "app.jobs.tasks.run_catalog_collection":
            jobs.append(job)

    def latest_timestamp(job) -> float:
        timestamp = job.ended_at or job.started_at or job.enqueued_at
        return timestamp.timestamp() if timestamp else 0

    jobs.sort(key=latest_timestamp, reverse=True)
    return [_catalog_job_payload(job) for job in jobs[: min(max(limit, 1), 100)]]
