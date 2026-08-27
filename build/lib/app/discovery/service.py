from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    DiscoveryRun,
    Flyer,
    FlyerPage,
    FlyerSource,
    FlyerStatus,
    Retailer,
    RunStatus,
    Store,
)
from app.downloader.service import DownloadService, flyer_content_hash
from app.jobs.queue import enqueue_extraction
from app.providers import PROVIDERS


async def discover_source(db: Session, source_id: UUID, enqueue: bool = True) -> UUID:
    source = db.get(FlyerSource, source_id)
    if source is None:
        raise ValueError("Source not found")
    run = DiscoveryRun(source_id=source.id, status=RunStatus.RUNNING, started_at=datetime.now(UTC))
    db.add(run)
    db.commit()
    try:
        provider_class = PROVIDERS.get(source.provider_type)
        if provider_class is None:
            raise ValueError(f"Unknown provider type {source.provider_type}")
        discovered = await provider_class().discover(source)
        run.flyers_discovered = len(discovered)
        store, retailer = db.execute(
            select(Store, Retailer)
            .join(Retailer, Store.retailer_id == Retailer.id)
            .where(Store.id == source.store_id)
        ).one()
        downloader = DownloadService()
        item_errors: list[str] = []
        for item in discovered:
            flyer = Flyer(
                store_id=source.store_id,
                source_id=source.id,
                status=FlyerStatus.DOWNLOADING,
                valid_from=item.valid_from,
                valid_until=item.valid_until,
            )
            db.add(flyer)
            db.flush()
            from app.core.config import get_settings

            root = Path(get_settings().flyer_storage_path)
            folder = root / "raw" / retailer.slug / str(store.id) / str(flyer.id)
            try:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "source.html").write_text(item.source_html, encoding="utf-8")
                hashes = []
                page_models = []
                for page in await provider_class().get_pages(item):
                    asset = await downloader.download(
                        page.url, folder / f"page-{page.page_number:03d}"
                    )
                    hashes.append(asset.sha256)
                    page_models.append(
                        FlyerPage(
                            flyer_id=flyer.id,
                            page_number=page.page_number,
                            source_url=page.url,
                            local_path=str(asset.path),
                            sha256=asset.sha256,
                            mime_type=asset.mime_type,
                            width=asset.width,
                            height=asset.height,
                            file_size=asset.file_size,
                            etag=asset.etag,
                            last_modified=asset.last_modified,
                        )
                    )
                if not hashes:
                    raise ValueError("Provider returned a flyer without pages")
                flyer.content_hash = flyer_content_hash(hashes)
                duplicate = db.scalar(
                    select(Flyer.id).where(
                        Flyer.store_id == flyer.store_id,
                        Flyer.content_hash == flyer.content_hash,
                        Flyer.id != flyer.id,
                    )
                )
                if duplicate:
                    db.delete(flyer)
                    db.commit()
                    rmtree(folder, ignore_errors=True)
                    continue
                db.add_all(page_models)
                run.pages_downloaded += len(page_models)
                flyer.status = FlyerStatus.DOWNLOADED
                run.flyers_new += 1
                db.commit()
                if enqueue:
                    enqueue_extraction(flyer.id)
                    flyer.status = FlyerStatus.QUEUED
                    run.jobs_created += 1
                db.commit()
            except Exception as exc:
                db.rollback()
                failed = db.get(Flyer, flyer.id)
                if failed is None:
                    failed = Flyer(
                        id=flyer.id,
                        store_id=source.store_id,
                        source_id=source.id,
                        status=FlyerStatus.DOWNLOAD_FAILED,
                        valid_from=item.valid_from,
                        valid_until=item.valid_until,
                    )
                    db.add(failed)
                else:
                    failed.status = FlyerStatus.DOWNLOAD_FAILED
                item_errors.append(str(exc))
                db.commit()
        source.last_checked_at = datetime.now(UTC)
        run.status = RunStatus.PARTIAL_SUCCESS if item_errors else RunStatus.SUCCESS
        run.error = "; ".join(item_errors) or None
        run.finished_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        run.status = RunStatus.FAILED
        run.error = str(exc)
        run.finished_at = datetime.now(UTC)
        db.commit()
        raise
    return run.id
