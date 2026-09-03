"""Target catalog model described in docs/CATALOG-COLLECTION-AND-ENRICHMENT.md.

These tables live alongside the legacy flyer/catalog model. Collection writes go
through ``app.catalog.v2.ingest``; the enrichment and resolution tables exist so
the schema matches the documented target architecture and future phases can be
built without another migration wave.

The new tables use ``bigint`` identities while referencing the legacy
``retailers``/``stores`` UUID primary keys.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID as _UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class _BigIntId:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class CatalogSource(_BigIntId, Base):
    __tablename__ = "catalog_sources"
    retailer_id: Mapped[_UUID] = mapped_column(ForeignKey("retailers.id"))
    code: Mapped[str] = mapped_column(String(120))
    provider_type: Mapped[str] = mapped_column(String(50))
    base_url: Mapped[str] = mapped_column(Text)
    public_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("retailer_id", "code"),)


class CollectionTarget(_BigIntId, Base):
    __tablename__ = "collection_targets"
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_sources.id"))
    store_id: Mapped[_UUID] = mapped_column(ForeignKey("stores.id"))
    target_key: Mapped[str] = mapped_column(String(120))
    external_store_id: Mapped[str | None] = mapped_column(String(120))
    external_store_code: Mapped[str | None] = mapped_column(String(120))
    seller_id: Mapped[str | None] = mapped_column(String(120))
    sales_channel: Mapped[str | None] = mapped_column(String(120))
    reference_postal_code: Mapped[str | None] = mapped_column(String(20))
    public_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_group: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("source_id", "target_key"),)


class CollectionRun(_BigIntId, Base):
    __tablename__ = "collection_runs"
    target_id: Mapped[int] = mapped_column(ForeignKey("collection_targets.id"))
    ingestion_key: Mapped[_UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(30))
    trigger_type: Mapped[str] = mapped_column(String(30), default="scheduled")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    pages_expected: Mapped[int | None] = mapped_column(Integer)
    pages_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    items_priced: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_changed: Mapped[int] = mapped_column(Integer, default=0)
    items_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    price_periods_created: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    collector_version: Mapped[str] = mapped_column(String(50))
    payload_uri: Mapped[str | None] = mapped_column(Text)
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("target_id", "ingestion_key"),)


class CollectionRunError(_BigIntId, Base):
    __tablename__ = "collection_run_errors"
    run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    scope_type: Mapped[str] = mapped_column(String(50))
    scope_key: Mapped[str] = mapped_column(String(255))
    page_number: Mapped[int | None] = mapped_column(Integer)
    cursor: Mapped[str | None] = mapped_column(String(255))
    endpoint: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    error_class: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)


class SourceProduct(_BigIntId, Base):
    __tablename__ = "source_products"
    source_id: Mapped[int] = mapped_column(ForeignKey("catalog_sources.id"))
    external_id: Mapped[str] = mapped_column(String(120))
    internal_code: Mapped[str | None] = mapped_column(String(120))
    current_version_id: Mapped[int | None] = mapped_column(BigInteger)
    current_product_url: Mapped[str | None] = mapped_column(Text)
    current_image_url: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)


class SourceProductVersion(_BigIntId, Base):
    __tablename__ = "source_product_versions"
    source_product_id: Mapped[int] = mapped_column(ForeignKey("source_products.id"))
    version: Mapped[int] = mapped_column(Integer)
    raw_name: Mapped[str] = mapped_column(Text)
    raw_brand: Mapped[str | None] = mapped_column(String(160))
    raw_gtin: Mapped[str | None] = mapped_column(String(32))
    raw_categories: Mapped[list] = mapped_column(JSONB, default=list)
    raw_measure: Mapped[str | None] = mapped_column(String(50))
    raw_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    raw_unit: Mapped[str | None] = mapped_column(String(30))
    raw_package: Mapped[str | None] = mapped_column(String(120))
    raw_product_url: Mapped[str | None] = mapped_column(Text)
    raw_image_url: Mapped[str | None] = mapped_column(Text)
    raw_attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    identity_input_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("source_product_id", "version"),
        UniqueConstraint("id", "source_product_id"),
    )


class StoreListing(_BigIntId, Base):
    __tablename__ = "store_listings"
    target_id: Mapped[int] = mapped_column(ForeignKey("collection_targets.id"))
    source_product_id: Mapped[int] = mapped_column(ForeignKey("source_products.id"))
    external_listing_id: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    availability: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    stock_current: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    price_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_runs.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("target_id", "source_product_id"),)


class PricePeriod(_BigIntId, Base):
    __tablename__ = "price_periods"
    store_listing_id: Mapped[int] = mapped_column(ForeignKey("store_listings.id"))
    version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"))
    last_run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"))
    confirmation_count: Mapped[int] = mapped_column(BigInteger, default=1)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    regular_price_cents: Mapped[int | None] = mapped_column(Integer)
    effective_price_cents: Mapped[int] = mapped_column(Integer)
    best_conditional_price_cents: Mapped[int | None] = mapped_column(Integer)
    normalized_unit_price_micros: Mapped[int | None] = mapped_column(BigInteger)
    price_basis_unit: Mapped[str | None] = mapped_column(String(20))
    price_terms: Mapped[list] = mapped_column(JSONB, default=list)
    promotion_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promotion_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("store_listing_id", "version"),)


class Department(_BigIntId, Base):
    __tablename__ = "departments"
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductConcept(_BigIntId, Base):
    __tablename__ = "product_concepts"
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    default_comparison_unit: Mapped[str | None] = mapped_column(String(20))
    identity_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductVariant(_BigIntId, Base):
    __tablename__ = "product_variants"
    concept_id: Mapped[int] = mapped_column(ForeignKey("product_concepts.id"))
    canonical_name: Mapped[str] = mapped_column(String(255))
    species: Mapped[str | None] = mapped_column(String(80))
    cut: Mapped[str | None] = mapped_column(String(80))
    presentation: Mapped[str | None] = mapped_column(String(80))
    conservation: Mapped[str | None] = mapped_column(String(80))
    bone_state: Mapped[str | None] = mapped_column(String(80))
    seasoning_state: Mapped[str | None] = mapped_column(String(80))
    sale_mode: Mapped[str | None] = mapped_column(String(80))
    comparison_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    comparison_unit: Mapped[str | None] = mapped_column(String(20))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    identity_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("id", "concept_id"),)


class TradeItem(_BigIntId, Base):
    __tablename__ = "trade_items"
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    canonical_name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(160))
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    net_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    package_type: Mapped[str | None] = mapped_column(String(80))
    identity_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("id", "variant_id"),)


class TradeItemIdentifier(_BigIntId, Base):
    __tablename__ = "trade_item_identifiers"
    trade_item_id: Mapped[int] = mapped_column(ForeignKey("trade_items.id"))
    scheme: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(120))


class NormalizedProductVersion(_BigIntId, Base):
    __tablename__ = "normalized_product_versions"
    source_product_version_id: Mapped[int] = mapped_column(
        ForeignKey("source_product_versions.id")
    )
    normalizer_version: Mapped[str] = mapped_column(String(50))
    pipeline_version: Mapped[str] = mapped_column(String(50))
    normalized_name: Mapped[str] = mapped_column(Text)
    normalized_brand: Mapped[str | None] = mapped_column(String(160))
    validated_gtin: Mapped[str | None] = mapped_column(String(32))
    concept_hint: Mapped[str | None] = mapped_column(String(200))
    species: Mapped[str | None] = mapped_column(String(80))
    cut: Mapped[str | None] = mapped_column(String(80))
    presentation: Mapped[str | None] = mapped_column(String(80))
    conservation: Mapped[str | None] = mapped_column(String(80))
    bone_state: Mapped[str | None] = mapped_column(String(80))
    seasoning_state: Mapped[str | None] = mapped_column(String(80))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    sale_mode: Mapped[str | None] = mapped_column(String(80))
    package_type: Mapped[str | None] = mapped_column(String(80))
    identity_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    quality_flags: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "source_product_version_id", "normalizer_version", "pipeline_version"
        ),
        UniqueConstraint("id", "source_product_version_id"),
    )


class ResolutionCase(_BigIntId, Base):
    __tablename__ = "resolution_cases"
    source_product_version_id: Mapped[int] = mapped_column(BigInteger)
    normalized_product_version_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchCandidate(_BigIntId, Base):
    __tablename__ = "match_candidates"
    resolution_case_id: Mapped[int] = mapped_column(ForeignKey("resolution_cases.id"))
    concept_id: Mapped[int] = mapped_column(ForeignKey("product_concepts.id"))
    variant_id: Mapped[int | None] = mapped_column(BigInteger)
    trade_item_id: Mapped[int | None] = mapped_column(BigInteger)
    candidate_method: Mapped[str] = mapped_column(String(50))
    deterministic_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    rank: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiAssessment(_BigIntId, Base):
    __tablename__ = "ai_assessments"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("match_candidates.id"))
    decision: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    extracted_evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    model: Mapped[str] = mapped_column(String(120))
    model_revision: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(50))
    request_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    raw_response_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProductResolution(_BigIntId, Base):
    __tablename__ = "product_resolutions"
    source_product_version_id: Mapped[int] = mapped_column(BigInteger)
    normalized_product_version_id: Mapped[int] = mapped_column(BigInteger)
    concept_id: Mapped[int] = mapped_column(ForeignKey("product_concepts.id"))
    variant_id: Mapped[int | None] = mapped_column(BigInteger)
    trade_item_id: Mapped[int | None] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    normalizer_version: Mapped[str] = mapped_column(String(50))
    pipeline_version: Mapped[str] = mapped_column(String(50))
    approved_by: Mapped[str] = mapped_column(String(255))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decision_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    supersedes_resolution_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("id", "source_product_version_id"),
        UniqueConstraint("source_product_version_id", "decision_hash"),
    )


class CurrentProductResolution(Base):
    __tablename__ = "current_product_resolutions"
    source_product_version_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    product_resolution_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    changed_by: Mapped[str] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
