import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class FlyerStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    EXPIRED = "EXPIRED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    ACQUISITION_BLOCKED = "ACQUISITION_BLOCKED"


class IdModel:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Retailer(IdModel, Base):
    __tablename__ = "retailers"
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Store(IdModel, Base):
    __tablename__ = "stores"
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"))
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogRun(IdModel, Base):
    __tablename__ = "catalog_runs"
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"))
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stores.id"))
    provider_type: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[RunStatus] = mapped_column(SqlEnum(RunStatus), default=RunStatus.SUCCESS)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    priced_product_count: Mapped[int] = mapped_column(Integer, default=0)
    source_context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("retailer_id", "provider_type", "source_url", "collected_at"),
    )


class CatalogProduct(IdModel, Base):
    __tablename__ = "catalog_products"
    retailer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("retailers.id"))
    external_id: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(160))
    categories: Mapped[list] = mapped_column(JSONB, default=list)
    department: Mapped[str] = mapped_column(String(80), default="Outros", index=True)
    measure: Mapped[str | None] = mapped_column(String(50))
    product_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    ean: Mapped[str | None] = mapped_column(String(32))
    internal_code: Mapped[str | None] = mapped_column(String(120))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("retailer_id", "external_id"),)


class CatalogPriceObservation(IdModel, Base):
    __tablename__ = "catalog_price_observations"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_runs.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_products.id"))
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stores.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available: Mapped[bool] = mapped_column(Boolean)
    stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    regular_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sales_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    previous_sales_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_change_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_change_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    offer_tags: Mapped[list] = mapped_column(JSONB, default=list)
    discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tier_prices: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("run_id", "product_id"),)


class FlyerSource(IdModel, Base):
    __tablename__ = "flyer_sources"
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    provider_type: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiscoveryRun(IdModel, Base):
    __tablename__ = "discovery_runs"
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyer_sources.id"))
    status: Mapped[RunStatus] = mapped_column(SqlEnum(RunStatus), default=RunStatus.PENDING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    flyers_discovered: Mapped[int] = mapped_column(Integer, default=0)
    flyers_new: Mapped[int] = mapped_column(Integer, default=0)
    pages_downloaded: Mapped[int] = mapped_column(Integer, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)


class Flyer(IdModel, Base):
    __tablename__ = "flyers"
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyer_sources.id"))
    status: Mapped[FlyerStatus] = mapped_column(
        SqlEnum(FlyerStatus), default=FlyerStatus.DISCOVERED
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FlyerPage(IdModel, Base):
    __tablename__ = "flyer_pages"
    flyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyers.id"))
    page_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    file_size: Mapped[int] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    annotation_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    annotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("flyer_id", "page_number"),)


class OfferRegionAnnotation(IdModel, Base):
    __tablename__ = "offer_region_annotations"
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyer_pages.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="MANUAL")
    confidence: Mapped[float | None]
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("page_id", "sequence"),)


class ExtractionRun(IdModel, Base):
    __tablename__ = "extraction_runs"
    flyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyers.id"))
    status: Mapped[RunStatus] = mapped_column(SqlEnum(RunStatus), default=RunStatus.PENDING)
    strategy: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    preferred: Mapped[bool] = mapped_column(Boolean, default=True)


class ExtractionAttempt(IdModel, Base):
    __tablename__ = "extraction_attempts"
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.id"))
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyer_pages.id"))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(50))
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed_response: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


class ProductOffer(IdModel, Base):
    __tablename__ = "product_offers"
    flyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyers.id"))
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("flyer_pages.id"))
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_runs.id"))
    raw_name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    variant: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    llm_confidence: Mapped[float | None]
    validation_confidence: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfferPackage(IdModel, Base):
    __tablename__ = "offer_packages"
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_offers.id"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String(30))
    raw_text: Mapped[str | None] = mapped_column(Text)


class OfferPrice(IdModel, Base):
    __tablename__ = "offer_prices"
    offer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_offers.id"))
    type: Mapped[str] = mapped_column(String(30))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    previous_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    minimum_quantity: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
