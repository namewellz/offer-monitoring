"""Projeta a identidade canônica do normalizador dentro do read model.

O normalizador é um passo em lote (o dicionário de marcas e os grupos de cobertura
dependem do corpus inteiro), então ele não roda dentro do ingest. Depois de
gravar ``normalized_product_versions``, este módulo copia os campos derivados
para ``store_listings`` — a tela passa a ler uma única tabela.

Nada aqui usa LLM: é só cópia de campos já calculados por regras.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.canonical.normalize import NORMALIZER_VERSION, PIPELINE_VERSION

# Quantidade na unidade base: g (peso), ml (volume) ou un (contagem).
# ``pack_qty`` multiplica porque o preço observado é o da embalagem vendida.
_PROJECT_SQL = """
UPDATE store_listings sl
SET identity_key = n.match_key,
    canonical_name = n.normalized_name,
    coverage_group = n.coverage_group,
    comparison_quantity = q.quantity,
    comparison_unit = q.unit,
    unit_price_micros = CASE
        WHEN q.quantity IS NOT NULL AND q.quantity > 0
         AND sl.effective_price_cents IS NOT NULL
        THEN round(sl.effective_price_cents * 10000.0 / q.quantity)
    END
FROM source_products sp
JOIN normalized_product_versions n
  ON n.source_product_version_id = sp.current_version_id
 AND n.normalizer_version = :version
 AND n.pipeline_version = :pipeline
CROSS JOIN LATERAL (
    SELECT
        CASE n.size_unit
            WHEN 'g' THEN n.size_value
            WHEN 'kg' THEN n.size_value * 1000
            WHEN 'mg' THEN n.size_value / 1000
            WHEN 'ml' THEN n.size_value
            WHEN 'l' THEN n.size_value * 1000
            WHEN 'lt' THEN n.size_value * 1000
            WHEN 'cl' THEN n.size_value * 10
            WHEN 'un' THEN n.size_value
            WHEN 'dz' THEN n.size_value * 12
            WHEN 'peca' THEN n.size_value
            WHEN 'capsula' THEN n.size_value
            WHEN 'tablete' THEN n.size_value
            WHEN 'folha' THEN n.size_value
            WHEN 'sache' THEN n.size_value
            WHEN 'rolo' THEN n.size_value
            WHEN 'saco' THEN n.size_value
        END * COALESCE(n.pack_qty, 1) AS quantity,
        CASE n.size_unit
            WHEN 'g' THEN 'g'
            WHEN 'kg' THEN 'g'
            WHEN 'mg' THEN 'g'
            WHEN 'ml' THEN 'ml'
            WHEN 'l' THEN 'ml'
            WHEN 'lt' THEN 'ml'
            WHEN 'cl' THEN 'ml'
            WHEN 'un' THEN 'un'
            WHEN 'dz' THEN 'un'
            WHEN 'peca' THEN 'un'
            WHEN 'capsula' THEN 'un'
            WHEN 'tablete' THEN 'un'
            WHEN 'folha' THEN 'un'
            WHEN 'sache' THEN 'un'
            WHEN 'rolo' THEN 'un'
            WHEN 'saco' THEN 'un'
        END AS unit
) q
WHERE sl.source_product_id = sp.id
  AND sl.active
"""

_PROJECT_PRODUCTS_SQL = _PROJECT_SQL + "  AND sp.id = ANY(:product_ids)\n"

# Uma linha por produto canônico. Reconstruída ao fim de cada projeção para a tela
# ler uma tabela pequena em vez de agregar 440k listings por requisição.
_REFRESH_SQL = """
INSERT INTO canonical_products (
    identity_key, canonical_name, department, coverage_group, comparison_unit,
    offers, retailers, min_unit_price_micros, max_unit_price_micros, refreshed_at
)
SELECT sl.identity_key,
       mode() WITHIN GROUP (ORDER BY sl.canonical_name),
       mode() WITHIN GROUP (ORDER BY sl.department),
       min(sl.coverage_group),
       min(sl.comparison_unit),
       count(DISTINCT ROW(sl.retailer_slug, sl.store_name, sl.product_name)) AS offers,
       count(DISTINCT sl.retailer_slug) AS retailers,
       min(sl.unit_price_micros),
       max(sl.unit_price_micros),
       now()
  FROM store_listings sl
 WHERE sl.active
   AND sl.identity_key IS NOT NULL
   AND sl.effective_price_cents IS NOT NULL
   AND (sl.store_region_bucket IS NULL OR sl.store_region_bucket <> 'fora')
 GROUP BY sl.identity_key
"""


_REFRESH_DROP_INDEXES = ("ix_cp_offers", "ix_cp_group_offers")

_REFRESH_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_cp_offers "
    "ON canonical_products (offers DESC, canonical_name)",
    "CREATE INDEX IF NOT EXISTS ix_cp_group_offers "
    "ON canonical_products (coverage_group, offers DESC)",
)


def refresh_canonical_products(db: Session) -> int:
    """Reconstrói o agregado da lista canônica. Idempotente.

    Os índices são derrubados e recriados em volta do INSERT: manter btree durante
    uma carga de 165k linhas custa mais que reconstruí-los no final.
    """
    for index in _REFRESH_DROP_INDEXES:
        db.execute(text(f"DROP INDEX IF EXISTS {index}"))
    db.execute(text("TRUNCATE canonical_products"))
    db.execute(text(_REFRESH_SQL))
    for statement in _REFRESH_CREATE_INDEXES:
        db.execute(text(statement))
    db.commit()
    db.execute(text("ANALYZE canonical_products"))
    db.commit()
    return int(
        db.scalar(text("SELECT count(*) FROM canonical_products")) or 0
    )


def project_all(db: Session) -> int:
    """Projeta a identidade canônica de todos os listings ativos."""
    result = db.execute(
        text(_PROJECT_SQL),
        {"version": NORMALIZER_VERSION, "pipeline": PIPELINE_VERSION},
    )
    db.commit()
    refresh_canonical_products(db)
    return int(result.rowcount or 0)


def project_products(db: Session, product_ids: list[int]) -> int:
    """Projeta só os produtos informados (usado pelo job incremental)."""
    if not product_ids:
        return 0
    result = db.execute(
        text(_PROJECT_PRODUCTS_SQL),
        {
            "version": NORMALIZER_VERSION,
            "pipeline": PIPELINE_VERSION,
            "product_ids": product_ids,
        },
    )
    db.commit()
    refresh_canonical_products(db)
    return int(result.rowcount or 0)


def project_retailer(db: Session, retailer_slug: str) -> int:
    """Projeta todos os produtos ativos de uma rede (após o normalize da coleta)."""
    rows = db.execute(
        text(
            """
            SELECT sp.id
              FROM source_products sp
              JOIN catalog_sources cs ON cs.id = sp.source_id
              JOIN retailers r ON r.id = cs.retailer_id
             WHERE sp.active AND r.slug = :slug
            """
        ),
        {"slug": retailer_slug},
    ).scalars().all()
    return project_products(db, [int(value) for value in rows])
