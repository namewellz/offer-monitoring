from uuid import UUID

from redis import Redis
from rq import Queue

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


def catalog_collection_job(job_id: str) -> dict | None:
    job = get_queue().fetch_job(job_id)
    if job is None:
        return None
    status = job.get_status(refresh=True)
    status = status.value if hasattr(status, "value") else str(status)
    return {
        "job_id": job.id,
        "status": status,
        "retailer": job.args[0] if job.args else None,
        "result": job.result if status == "finished" else None,
        "error": job.exc_info.splitlines()[-1] if status == "failed" and job.exc_info else None,
    }
