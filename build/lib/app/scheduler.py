from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.models import FlyerSource
from app.db.session import SessionLocal
from app.jobs.queue import enqueue_catalog_collection, enqueue_discovery

CATALOG_RETAILERS = (
    "arena-atacado",
    "goodbom",
    "atacadao",
    "savegnago",
    "davitta",
    "assai",
    "tenda",
    "sao-vicente",
)


def enqueue_sources(source_ids, enqueue=enqueue_discovery) -> list[Exception]:
    errors = []
    for source_id in source_ids:
        try:
            enqueue(source_id)
        except Exception as exc:
            errors.append(exc)
    return errors


def schedule_discovery() -> None:
    with SessionLocal() as db:
        enqueue_sources(db.scalars(select(FlyerSource.id).where(FlyerSource.active)).all())


def enqueue_catalogs(
    retailers: tuple[str, ...] = CATALOG_RETAILERS,
    enqueue=enqueue_catalog_collection,
) -> list[Exception]:
    errors = []
    for retailer_slug in retailers:
        try:
            enqueue(retailer_slug)
        except Exception as exc:
            errors.append(exc)
    return errors


def schedule_catalog_collections() -> None:
    enqueue_catalogs()


def add_cron_job(scheduler, function, cron: str, **kwargs) -> None:
    minute, hour, day, month, weekday = cron.split()
    scheduler.add_job(
        function,
        "cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=weekday,
        **kwargs,
    )


if __name__ == "__main__":
    configure_logging()
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=ZoneInfo(settings.scheduler_timezone))
    if settings.discovery_enabled:
        add_cron_job(
            scheduler,
            schedule_discovery,
            settings.discovery_cron,
            id="flyer-discovery",
            replace_existing=True,
        )
    if settings.catalog_collection_enabled:
        add_cron_job(
            scheduler,
            schedule_catalog_collections,
            settings.catalog_collection_cron,
            id="catalog-collections",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    scheduler.start()
