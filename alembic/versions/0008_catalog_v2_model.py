"""Target catalog model v2 (see docs/CATALOG-COLLECTION-AND-ENRICHMENT.md).

Creates the collection, source-product/listing/price-period and canonical
identity tables described in section 16 of the architecture document. The
legacy catalog tables remain untouched; this migration builds the v2 model
beside them so a dual-write and shadow-read phase can follow.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_catalog_v2_model"
down_revision: str | None = "0007_canonical_departments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_DEPARTMENTS = (
    ("acougue", "Açougue"),
    ("bebidas", "Bebidas"),
    ("bazar-e-utilidades", "Bazar e Utilidades"),
    ("congelados", "Congelados"),
    ("doces-e-sobremesas", "Doces e Sobremesas"),
    ("frios-e-laticinios", "Frios e Laticínios"),
    ("higiene", "Higiene"),
    ("hortifruti", "Hortifruti"),
    ("limpeza", "Limpeza"),
    ("mercearia", "Mercearia"),
    ("padaria", "Padaria"),
    ("peixaria", "Peixaria"),
    ("pet-shop", "Pet Shop"),
    ("saudaveis-e-organicos", "Saudáveis e Orgânicos"),
    ("outros", "Outros"),
)


def upgrade() -> None:
    # --- 7. Coleta e origem -------------------------------------------------
    op.create_table(
        "catalog_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column(
            "public_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.id"]),
        sa.UniqueConstraint("retailer_id", "code", name="uq_catalog_sources_retailer_code"),
    )

    op.create_table(
        "collection_targets",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("external_store_id", sa.Text()),
        sa.Column("external_store_code", sa.Text()),
        sa.Column("seller_id", sa.Text()),
        sa.Column("sales_channel", sa.Text()),
        sa.Column("reference_postal_code", sa.Text()),
        sa.Column(
            "public_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schedule_group", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.UniqueConstraint("source_id", "target_key", name="uq_collection_targets_source_key"),
    )

    op.create_table(
        "collection_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("ingestion_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pages_expected", sa.Integer()),
        sa.Column("pages_succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pages_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_priced", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_changed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_unchanged", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "price_periods_created",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("collector_version", sa.Text(), nullable=False),
        sa.Column("payload_uri", sa.Text()),
        sa.Column("payload_sha256", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["target_id"], ["collection_targets.id"]),
        sa.UniqueConstraint("target_id", "ingestion_key", name="uq_collection_runs_target_key"),
    )
    op.create_index(
        "ix_collection_runs_target_started",
        "collection_runs",
        ["target_id", "started_at"],
    )

    op.create_table(
        "collection_run_errors",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("cursor", sa.Text()),
        sa.Column("endpoint", sa.Text()),
        sa.Column("http_status", sa.Integer()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("error_class", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["collection_runs.id"]),
        sa.UniqueConstraint("run_id", "sequence", name="uq_collection_run_errors_run_seq"),
    )

    # --- 8. Produto original e listing -------------------------------------
    op.create_table(
        "source_products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("internal_code", sa.Text()),
        sa.Column("current_version_id", sa.BigInteger()),
        sa.Column("current_product_url", sa.Text()),
        sa.Column("current_image_url", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["source_id"], ["catalog_sources.id"]),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_products_source_external"),
    )

    op.create_table(
        "source_product_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_product_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("raw_brand", sa.Text()),
        sa.Column("raw_gtin", sa.Text()),
        sa.Column(
            "raw_categories",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("raw_measure", sa.Text()),
        sa.Column("raw_quantity", sa.Numeric(14, 3)),
        sa.Column("raw_unit", sa.Text()),
        sa.Column("raw_package", sa.Text()),
        sa.Column("raw_product_url", sa.Text()),
        sa.Column("raw_image_url", sa.Text()),
        sa.Column(
            "raw_attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("raw_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("identity_input_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("first_run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["source_product_id"], ["source_products.id"]),
        sa.ForeignKeyConstraint(["first_run_id"], ["collection_runs.id"]),
        sa.UniqueConstraint("source_product_id", "version", name="uq_source_versions_product_ver"),
        sa.UniqueConstraint("id", "source_product_id", name="uq_source_versions_id_product"),
        sa.CheckConstraint("octet_length(raw_hash) = 32", name="ck_source_versions_raw_hash"),
        sa.CheckConstraint(
            "octet_length(identity_input_hash) = 32",
            name="ck_source_versions_identity_hash",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_source_versions_valid_window",
        ),
    )
    op.create_index(
        "uq_source_product_open_version",
        "source_product_versions",
        ["source_product_id"],
        unique=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )
    op.create_index(
        "ix_source_product_versions_hash",
        "source_product_versions",
        ["source_product_id", "raw_hash"],
    )

    op.add_column(
        "source_products",
        sa.Column("_unused", sa.Boolean(), nullable=True),
    )
    op.drop_column("source_products", "_unused")
    op.create_foreign_key(
        "fk_source_product_current_version",
        "source_products",
        "source_product_versions",
        ["current_version_id", "id"],
        ["id", "source_product_id"],
    )

    op.create_table(
        "store_listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("source_product_id", sa.BigInteger(), nullable=False),
        sa.Column("external_listing_id", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "availability",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column("stock_current", sa.Numeric(14, 3)),
        sa.Column("price_status", sa.Text(), nullable=False, server_default=sa.text("'UNKNOWN'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_run_id", sa.BigInteger()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["target_id"], ["collection_targets.id"]),
        sa.ForeignKeyConstraint(["source_product_id"], ["source_products.id"]),
        sa.ForeignKeyConstraint(["last_seen_run_id"], ["collection_runs.id"]),
        sa.UniqueConstraint("target_id", "source_product_id", name="uq_store_listings_target_product"),
        sa.CheckConstraint(
            "availability IN ('AVAILABLE', 'OUT_OF_STOCK', 'UNAVAILABLE', 'UNKNOWN')",
            name="ck_store_listings_availability",
        ),
        sa.CheckConstraint(
            "price_status IN ('KNOWN', 'UNKNOWN', 'UNAVAILABLE', 'WITHHELD')",
            name="ck_store_listings_price_status",
        ),
    )

    op.create_table(
        "price_periods",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("store_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("first_run_id", sa.BigInteger(), nullable=False),
        sa.Column("last_run_id", sa.BigInteger(), nullable=False),
        sa.Column("confirmation_count", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'BRL'")),
        sa.Column("regular_price_cents", sa.Integer()),
        sa.Column("effective_price_cents", sa.Integer(), nullable=False),
        sa.Column("best_conditional_price_cents", sa.Integer()),
        sa.Column("normalized_unit_price_micros", sa.BigInteger()),
        sa.Column("price_basis_unit", sa.Text()),
        sa.Column(
            "price_terms",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("promotion_valid_from", sa.DateTime(timezone=True)),
        sa.Column("promotion_valid_until", sa.DateTime(timezone=True)),
        sa.Column("state_hash", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["store_listing_id"], ["store_listings.id"]),
        sa.ForeignKeyConstraint(["first_run_id"], ["collection_runs.id"]),
        sa.ForeignKeyConstraint(["last_run_id"], ["collection_runs.id"]),
        sa.UniqueConstraint("store_listing_id", "version", name="uq_price_periods_listing_ver"),
        sa.CheckConstraint(
            "regular_price_cents IS NULL OR regular_price_cents > 0",
            name="ck_price_periods_regular_positive",
        ),
        sa.CheckConstraint("effective_price_cents > 0", name="ck_price_periods_effective_positive"),
        sa.CheckConstraint(
            "best_conditional_price_cents IS NULL OR best_conditional_price_cents > 0",
            name="ck_price_periods_conditional_positive",
        ),
        sa.CheckConstraint("octet_length(state_hash) = 32", name="ck_price_periods_state_hash"),
        sa.CheckConstraint("confirmation_count >= 1", name="ck_price_periods_confirmations"),
        sa.CheckConstraint(
            "last_confirmed_at >= started_at", name="ck_price_periods_confirmed_after_start"
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at", name="ck_price_periods_end_after_start"
        ),
    )
    op.create_index(
        "uq_price_period_open",
        "price_periods",
        ["store_listing_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_price_period_history",
        "price_periods",
        ["store_listing_id", "started_at"],
    )

    # --- 11-13. Identidade canônica ----------------------------------------
    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("parent_id", sa.BigInteger()),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["departments.id"]),
        sa.UniqueConstraint("code", name="uq_departments_code"),
        sa.UniqueConstraint("slug", name="uq_departments_slug"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_departments_parent"),
    )

    op.create_table(
        "product_concepts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("department_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("default_comparison_unit", sa.Text()),
        sa.Column(
            "identity_policy",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.UniqueConstraint("slug", name="uq_product_concepts_slug"),
    )

    op.create_table(
        "product_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("concept_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("species", sa.Text()),
        sa.Column("cut", sa.Text()),
        sa.Column("presentation", sa.Text()),
        sa.Column("conservation", sa.Text()),
        sa.Column("bone_state", sa.Text()),
        sa.Column("seasoning_state", sa.Text()),
        sa.Column("sale_mode", sa.Text()),
        sa.Column("comparison_quantity", sa.Numeric(14, 3)),
        sa.Column("comparison_unit", sa.Text()),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("identity_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["concept_id"], ["product_concepts.id"]),
        sa.UniqueConstraint("identity_hash", name="uq_product_variants_identity_hash"),
        sa.UniqueConstraint("id", "concept_id", name="uq_product_variants_id_concept"),
    )
    op.create_index(
        "ix_product_variants_concept",
        "product_variants",
        ["concept_id"],
        postgresql_where=sa.text("active = true"),
    )

    op.create_table(
        "trade_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text()),
        sa.Column("manufacturer", sa.Text()),
        sa.Column("net_quantity", sa.Numeric(14, 3)),
        sa.Column("unit", sa.Text()),
        sa.Column("package_type", sa.Text()),
        sa.Column("identity_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.UniqueConstraint("identity_hash", name="uq_trade_items_identity_hash"),
        sa.UniqueConstraint("id", "variant_id", name="uq_trade_items_id_variant"),
    )

    op.create_table(
        "trade_item_identifiers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("trade_item_id", sa.BigInteger(), nullable=False),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.Text()),
        sa.ForeignKeyConstraint(["trade_item_id"], ["trade_items.id"]),
        sa.CheckConstraint(
            "status IN ('VALID', 'CONFLICT', 'REVOKED')",
            name="ck_trade_item_identifiers_status",
        ),
    )
    op.create_index(
        "uq_valid_trade_item_identifier",
        "trade_item_identifiers",
        ["scheme", "value"],
        unique=True,
        postgresql_where=sa.text("status = 'VALID'"),
    )

    # --- 12. Enriquecimento e resolução ------------------------------------
    op.create_table(
        "normalized_product_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_product_version_id", sa.BigInteger(), nullable=False),
        sa.Column("normalizer_version", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("normalized_brand", sa.Text()),
        sa.Column("validated_gtin", sa.Text()),
        sa.Column("concept_hint", sa.Text()),
        sa.Column("species", sa.Text()),
        sa.Column("cut", sa.Text()),
        sa.Column("presentation", sa.Text()),
        sa.Column("conservation", sa.Text()),
        sa.Column("bone_state", sa.Text()),
        sa.Column("seasoning_state", sa.Text()),
        sa.Column("quantity", sa.Numeric(14, 3)),
        sa.Column("unit", sa.Text()),
        sa.Column("sale_mode", sa.Text()),
        sa.Column("package_type", sa.Text()),
        sa.Column("identity_fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["source_product_version_id"], ["source_product_versions.id"]
        ),
        sa.UniqueConstraint(
            "source_product_version_id",
            "normalizer_version",
            "pipeline_version",
            name="uq_normalized_versions_source_pipeline",
        ),
        sa.UniqueConstraint(
            "id", "source_product_version_id", name="uq_normalized_versions_id_source"
        ),
    )

    op.create_table(
        "resolution_cases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_product_version_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_product_version_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["normalized_product_version_id", "source_product_version_id"],
            ["normalized_product_versions.id", "normalized_product_versions.source_product_version_id"],
            name="fk_resolution_cases_normalized",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'AUTO_RESOLVED', 'NEEDS_REVIEW', "
            "'APPROVED', 'REJECTED', 'CONFLICT', 'FAILED')",
            name="ck_resolution_cases_status",
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= opened_at",
            name="ck_resolution_cases_resolved_after_open",
        ),
    )

    op.create_table(
        "match_candidates",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("resolution_case_id", sa.BigInteger(), nullable=False),
        sa.Column("concept_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger()),
        sa.Column("trade_item_id", sa.BigInteger()),
        sa.Column("candidate_method", sa.Text(), nullable=False),
        sa.Column("deterministic_score", sa.Numeric(6, 5)),
        sa.Column("similarity_score", sa.Numeric(6, 5)),
        sa.Column("final_score", sa.Numeric(6, 5)),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["resolution_case_id"], ["resolution_cases.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["product_concepts.id"]),
        sa.ForeignKeyConstraint(
            ["variant_id", "concept_id"],
            ["product_variants.id", "product_variants.concept_id"],
            name="fk_match_candidates_variant",
        ),
        sa.ForeignKeyConstraint(
            ["trade_item_id", "variant_id"],
            ["trade_items.id", "trade_items.variant_id"],
            name="fk_match_candidates_trade_item",
        ),
        sa.CheckConstraint(
            "trade_item_id IS NULL OR variant_id IS NOT NULL",
            name="ck_match_candidates_trade_needs_variant",
        ),
        sa.CheckConstraint(
            "deterministic_score IS NULL OR deterministic_score BETWEEN 0 AND 1",
            name="ck_match_candidates_deterministic_range",
        ),
        sa.CheckConstraint(
            "similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1",
            name="ck_match_candidates_similarity_range",
        ),
        sa.CheckConstraint(
            "final_score IS NULL OR final_score BETWEEN 0 AND 1",
            name="ck_match_candidates_final_range",
        ),
    )

    op.create_table(
        "ai_assessments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("candidate_id", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5)),
        sa.Column(
            "extracted_evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text()),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("raw_response_uri", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["match_candidates.id"]),
        sa.CheckConstraint(
            "decision IN ('SAME', 'RELATED', 'DIFFERENT', 'UNCERTAIN')",
            name="ck_ai_assessments_decision",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_ai_assessments_confidence_range",
        ),
    )

    op.create_table(
        "product_resolutions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_product_version_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_product_version_id", sa.BigInteger(), nullable=False),
        sa.Column("concept_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger()),
        sa.Column("trade_item_id", sa.BigInteger()),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5)),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("normalizer_version", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decision_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("supersedes_resolution_id", sa.BigInteger()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["product_concepts.id"]),
        sa.ForeignKeyConstraint(
            ["normalized_product_version_id", "source_product_version_id"],
            ["normalized_product_versions.id", "normalized_product_versions.source_product_version_id"],
            name="fk_product_resolutions_normalized",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id", "concept_id"],
            ["product_variants.id", "product_variants.concept_id"],
            name="fk_product_resolutions_variant",
        ),
        sa.ForeignKeyConstraint(
            ["trade_item_id", "variant_id"],
            ["trade_items.id", "trade_items.variant_id"],
            name="fk_product_resolutions_trade_item",
        ),
        sa.UniqueConstraint("id", "source_product_version_id", name="uq_product_resolutions_id_source"),
        sa.UniqueConstraint(
            "source_product_version_id",
            "decision_hash",
            name="uq_product_resolutions_source_decision",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_resolution_id", "source_product_version_id"],
            ["product_resolutions.id", "product_resolutions.source_product_version_id"],
            name="fk_product_resolutions_supersedes",
        ),
        sa.CheckConstraint(
            "trade_item_id IS NULL OR variant_id IS NOT NULL",
            name="ck_product_resolutions_trade_needs_variant",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_product_resolutions_confidence_range",
        ),
        sa.CheckConstraint(
            "octet_length(decision_hash) = 32",
            name="ck_product_resolutions_decision_hash",
        ),
        sa.CheckConstraint(
            "supersedes_resolution_id IS NULL OR supersedes_resolution_id <> id",
            name="ck_product_resolutions_no_self_supersede",
        ),
    )

    op.create_table(
        "current_product_resolutions",
        sa.Column("source_product_version_id", sa.BigInteger(), primary_key=True),
        sa.Column("product_resolution_id", sa.BigInteger(), nullable=False),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["source_product_version_id"], ["source_product_versions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["product_resolution_id", "source_product_version_id"],
            ["product_resolutions.id", "product_resolutions.source_product_version_id"],
            name="fk_current_resolution_pointer",
        ),
        sa.UniqueConstraint("product_resolution_id", name="uq_current_resolution_id"),
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION forbid_product_resolution_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'product_resolutions is append-only; insert a superseding decision';
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_product_resolutions_append_only
            BEFORE UPDATE OR DELETE ON product_resolutions
            FOR EACH ROW EXECUTE FUNCTION forbid_product_resolution_mutation();
            """
        )
    )

    departments = sa.table(
        "departments",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("slug", sa.Text()),
    )
    op.bulk_insert(
        departments,
        [
            {"code": slug, "name": name, "slug": slug}
            for slug, name in CANONICAL_DEPARTMENTS
        ],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_product_resolutions_append_only ON product_resolutions")
    op.execute("DROP FUNCTION IF EXISTS forbid_product_resolution_mutation()")
    op.drop_table("current_product_resolutions")
    op.drop_table("product_resolutions")
    op.drop_table("ai_assessments")
    op.drop_table("match_candidates")
    op.drop_table("resolution_cases")
    op.drop_table("normalized_product_versions")
    op.drop_table("trade_item_identifiers")
    op.drop_table("trade_items")
    op.drop_table("product_variants")
    op.drop_table("product_concepts")
    op.drop_table("departments")
    op.drop_table("price_periods")
    op.drop_table("store_listings")
    op.drop_constraint(
        "fk_source_product_current_version", "source_products", type_="foreignkey"
    )
    op.drop_table("source_product_versions")
    op.drop_table("source_products")
    op.drop_table("collection_run_errors")
    op.drop_index("ix_collection_runs_target_started", table_name="collection_runs")
    op.drop_table("collection_runs")
    op.drop_table("collection_targets")
    op.drop_table("catalog_sources")
