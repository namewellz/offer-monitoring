from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy import canonical_offer_category
from app.core.config import get_settings
from app.core.exceptions import ExtractionError
from app.db.models import (
    ExtractionAttempt,
    ExtractionRun,
    Flyer,
    FlyerPage,
    FlyerStatus,
    OfferPackage,
    OfferPrice,
    ProductOffer,
    RunStatus,
)
from app.extraction.consolidator import consolidate_offers
from app.extraction.ollama_client import OllamaVisionClient
from app.extraction.schemas import PriceCondition
from app.extraction.tiling import create_tiles
from app.normalization.validators import validation_confidence


def is_expired(valid_until: date | None, today: date | None = None) -> bool:
    return valid_until is not None and valid_until < (today or date.today())


def _prompt() -> str:
    return (Path(__file__).parents[2] / "prompts" / "flyer_extraction_v1.txt").read_text(
        encoding="utf-8"
    )


def _tile_prompt(tile_number: int) -> str:
    return (
        _prompt()
        + "\nA imagem e uma regiao sobreposta da pagina original (parte "
        + f"{tile_number} de 4). Extraia somente ofertas completamente legiveis nesta imagem. "
        + "Nao tente reconstruir produtos cortados nas bordas; uma regiao vizinha os preserva."
    )


def reliable_prices(prices: list[PriceCondition]) -> list[PriceCondition]:
    """Drops unsupported duplicate minimum-quantity conditions produced by the model."""
    unit_values = {price.price for price in prices if price.type == "UNIT_PRICE"}
    return [
        price
        for price in prices
        if not (
            price.type == "MIN_QUANTITY"
            and price.price in unit_values
            and not (price.description or "").strip()
        )
    ]


async def extract_flyer(
    db: Session, flyer_id: UUID, force: bool = False, strategy: str | None = None
) -> UUID | None:
    flyer = db.get(Flyer, flyer_id)
    if flyer is None:
        raise ValueError("Flyer not found")
    if flyer.status == FlyerStatus.PROCESSED and not force:
        return None
    requested_strategy = strategy or get_settings().extraction_mode
    if requested_strategy == "auto":
        requested_strategy = "tiles"
    if requested_strategy not in {"full_page", "tiles"}:
        raise ValueError(f"Unsupported extraction strategy: {requested_strategy}")
    for previous in db.scalars(
        select(ExtractionRun).where(
            ExtractionRun.flyer_id == flyer.id, ExtractionRun.preferred.is_(True)
        )
    ).all():
        previous.preferred = False
    run = ExtractionRun(
        flyer_id=flyer.id,
        status=RunStatus.RUNNING,
        strategy=requested_strategy,
        model=get_settings().ollama_model,
        prompt_version="flyer_extraction_v1",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    flyer.status = FlyerStatus.PROCESSING
    db.commit()
    client = OllamaVisionClient()
    try:
        if not await client.health():
            raise ExtractionError("Ollama is unavailable or unhealthy")
        pages = db.scalars(
            select(FlyerPage).where(FlyerPage.flyer_id == flyer.id).order_by(FlyerPage.page_number)
        ).all()
        valid_from = None
        valid_until = None
        successful_regions = 0
        failed_regions = 0
        for page in pages:
            with TemporaryDirectory(prefix=f"flyer-page-{page.page_number}-") as temp_dir:
                regions = (
                    [(None, Path(page.local_path), _prompt())]
                    if requested_strategy == "full_page"
                    else [
                        (tile.number, tile.path, _tile_prompt(tile.number))
                        for tile in create_tiles(
                            Path(page.local_path),
                            Path(temp_dir),
                            get_settings().tile_overlap_percent,
                        )
                    ]
                )
                page_offers = []
                for tile_number, image_path, prompt in regions:
                    attempt = ExtractionAttempt(
                        extraction_run_id=run.id,
                        page_id=page.id,
                        model=run.model,
                        prompt_version=(
                            run.prompt_version
                            if tile_number is None
                            else f"{run.prompt_version}_tile_{tile_number}"
                        ),
                        request_started_at=datetime.now(UTC),
                        status="RUNNING",
                    )
                    db.add(attempt)
                    db.commit()
                    try:
                        extraction, raw, duration = await client.extract(image_path, prompt)
                        attempt.status = "SUCCESS"
                        attempt.raw_response = raw
                        attempt.parsed_response = extraction.model_dump(mode="json")
                        attempt.duration_ms = duration
                        attempt.request_finished_at = datetime.now(UTC)
                        valid_from = extraction.valid_from or valid_from
                        valid_until = extraction.valid_until or valid_until
                        page_offers.extend(extraction.offers)
                        db.commit()
                        successful_regions += 1
                    except Exception as exc:
                        db.rollback()
                        attempt = db.get(ExtractionAttempt, attempt.id)
                        attempt.status = "FAILED"
                        attempt.error = str(exc)
                        attempt.request_finished_at = datetime.now(UTC)
                        db.commit()
                        failed_regions += 1

                for item in consolidate_offers(page_offers):
                    confidence = validation_confidence(
                        item.raw_product_name,
                        [price.price for price in item.prices],
                        [package.unit for package in item.packages],
                    )
                    offer = ProductOffer(
                        flyer_id=flyer.id,
                        page_id=page.id,
                        extraction_run_id=run.id,
                        raw_name=item.raw_product_name,
                        normalized_name=item.normalized_product_name,
                        brand=item.brand,
                        manufacturer=item.manufacturer,
                        category=canonical_offer_category(
                            item.category,
                            item.normalized_product_name or item.raw_product_name,
                        ),
                        description=item.description,
                        variant=item.variant,
                        raw_text=item.raw_text,
                        llm_confidence=item.confidence,
                        validation_confidence=confidence,
                    )
                    db.add(offer)
                    db.flush()
                    db.add_all(
                        [
                            OfferPackage(
                                offer_id=offer.id,
                                quantity=p.quantity,
                                unit=p.unit,
                                raw_text=p.raw_text,
                            )
                            for p in item.packages
                        ]
                    )
                    db.add_all(
                        [
                            OfferPrice(
                                offer_id=offer.id,
                                type=p.type,
                                price=p.price,
                                previous_price=p.previous_price,
                                minimum_quantity=p.minimum_quantity,
                                description=p.description,
                            )
                            for p in reliable_prices(item.prices)
                        ]
                    )
                db.commit()
        if not successful_regions:
            raise ExtractionError(f"Extraction failed for all {failed_regions} region(s)")
        flyer.valid_from = valid_from or flyer.valid_from
        flyer.valid_until = valid_until or flyer.valid_until
        flyer.status = (
            FlyerStatus.EXPIRED if is_expired(flyer.valid_until) else FlyerStatus.PROCESSED
        )
        run.status = RunStatus.PARTIAL_SUCCESS if failed_regions else RunStatus.SUCCESS
        if failed_regions:
            run.error = (
                f"{failed_regions} of {successful_regions + failed_regions} region(s) failed"
            )
        run.finished_at = datetime.now(UTC)
        db.commit()
        return run.id
    except Exception as exc:
        flyer.status = FlyerStatus.EXTRACTION_FAILED
        run.status = RunStatus.FAILED
        run.error = str(exc)
        run.finished_at = datetime.now(UTC)
        db.commit()
        raise
