"""Brand dictionary screen: list inferred brands and store approve, block, or alias.

Decisions go to ``brands``, ``brand_aliases`` and ``invalid_brands`` only.
The normalizer still builds its dictionary from the corpus until its version changes,
so saving here does not rewrite ``normalized_product_versions``.
"""

from __future__ import annotations

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.canonical.normalize import NORMALIZER_VERSION, PIPELINE_VERSION, alnum
from app.db.models_v2 import Brand, BrandAlias, InvalidBrand

_LIST_SQL = text(
    """
    SELECT n.brand_key,
           max(n.normalized_brand) AS name,
           count(*)::int AS items,
           count(DISTINCT r.slug)::int AS retailers,
           max(n.brand_origin) AS origin,
           (SELECT spv.raw_name
              FROM normalized_product_versions n2
              JOIN source_product_versions spv ON spv.id = n2.source_product_version_id
              JOIN source_products sp2
                ON sp2.current_version_id = spv.id
               AND sp2.active
             WHERE n2.brand_key = n.brand_key
               AND n2.normalizer_version = :v
               AND n2.pipeline_version = :p
             LIMIT 1) AS sample
      FROM normalized_product_versions n
      JOIN source_products sp
        ON sp.current_version_id = n.source_product_version_id
       AND sp.active
      JOIN catalog_sources cs ON cs.id = sp.source_id
      JOIN retailers r ON r.id = cs.retailer_id
     WHERE n.normalizer_version = :v
       AND n.pipeline_version = :p
       AND n.brand_key IS NOT NULL
       AND n.brand_key <> ''
       AND n.brand_key <> 'semmarca'
       AND (:origin = '' OR n.brand_origin = :origin)
       AND (
            :q = ''
            OR n.brand_key = :qkey
            OR coalesce(n.normalized_brand, '') ILIKE :qlike
       )
     GROUP BY n.brand_key
     ORDER BY count(*) DESC
     LIMIT :lim
    """
)

_COUNT_SQL = text(
    """
    SELECT count(DISTINCT n.brand_key)::int
      FROM normalized_product_versions n
      JOIN source_products sp
        ON sp.current_version_id = n.source_product_version_id
       AND sp.active
     WHERE n.normalizer_version = :v
       AND n.pipeline_version = :p
       AND n.brand_origin = 'inferred'
       AND n.brand_key IS NOT NULL
       AND n.brand_key <> ''
       AND n.brand_key <> 'semmarca'
    """
)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def normalize_action(payload: dict) -> dict:
    """Validate one dictionary edit. Raises ValueError with a short message."""
    action = str(payload.get("action") or "").strip()
    name = str(payload.get("name") or "").strip()[:160]
    target_name = str(payload.get("target") or "").strip()[:160]
    key = alnum(payload.get("key") or name)
    target_key = alnum(target_name)
    if action not in {"approve", "block", "alias"}:
        raise ValueError("ação desconhecida")
    if not key or key == "semmarca":
        raise ValueError("informe uma marca")
    if action == "alias":
        if not target_key:
            raise ValueError("informe a marca de destino")
        if target_key == key:
            action = "approve"
            name = target_name or name
    if not name:
        name = target_name or key
    return {
        "action": action,
        "key": key,
        "name": name,
        "target_name": target_name or name,
        "target_key": target_key or key,
    }


def _params(query: str) -> dict:
    query = query.strip()
    return {
        "v": NORMALIZER_VERSION,
        "p": PIPELINE_VERSION,
        "origin": "" if query else "inferred",
        "q": query,
        "qkey": alnum(query),
        "qlike": _like(query) if query else "",
        "lim": 200,
    }


def _decisions(db: Session) -> tuple[dict[str, dict], set[str]]:
    aliases = db.execute(
        select(
            BrandAlias.alias_key,
            BrandAlias.status,
            BrandAlias.alias,
            Brand.brand_key,
            Brand.name,
        ).join(Brand, Brand.id == BrandAlias.brand_id)
    ).all()
    by_key = {
        row.alias_key: {
            "status": row.status,
            "alias": row.alias,
            "brand_key": row.brand_key,
            "brand_name": row.name,
        }
        for row in aliases
    }
    blocked = set(db.scalars(select(InvalidBrand.brand_key)).all())
    return by_key, blocked


def _label(key: str, alias: dict | None, blocked: set[str]) -> tuple[str, str]:
    if key in blocked or (alias and alias["status"] == "blocked"):
        return "blocked", "bloqueada"
    if alias and alias["brand_key"] != key and alias["status"] == "approved":
        return "alias", f"apelido de {alias['brand_name']}"
    if alias and alias["status"] == "approved":
        return "approved", "aprovada"
    if alias and alias["status"] == "candidate":
        return "candidate", "candidata"
    return "candidate", "candidata"


def dictionary_page(db: Session, query: str = "") -> dict:
    query = query.strip()
    versions = {"v": NORMALIZER_VERSION, "p": PIPELINE_VERSION}
    total = int(db.execute(_COUNT_SQL, versions).scalar() or 0)
    rows = db.execute(_LIST_SQL, _params(query)).all()
    aliases, blocked = _decisions(db)
    items = []
    for row in rows:
        alias = aliases.get(row.brand_key)
        status, label = _label(row.brand_key, alias, blocked)
        items.append(
            {
                "key": row.brand_key,
                "name": row.name or row.brand_key,
                "items": int(row.items),
                "retailers": int(row.retailers),
                "origin": row.origin or "",
                "sample": row.sample or "",
                "status": status,
                "status_label": label,
            }
        )
    return {
        "q": query,
        "inferred_total": total,
        "shown": len(items),
        "decisions": len(aliases) + len(blocked),
        "rows": items,
        "normalizer_version": NORMALIZER_VERSION,
    }


def _upsert_brand(db: Session, key: str, name: str) -> Brand:
    brand = db.scalar(select(Brand).where(Brand.brand_key == key))
    if brand is None:
        brand = Brand(brand_key=key, name=name)
        db.add(brand)
        db.flush()
    else:
        brand.name = name
    return brand


def _upsert_alias(db: Session, brand: Brand, key: str, name: str, status: str) -> None:
    alias = db.scalar(select(BrandAlias).where(BrandAlias.alias_key == key))
    if alias is None:
        db.add(
            BrandAlias(
                brand_id=brand.id,
                alias=name,
                alias_key=key,
                status=status,
                source="dictionary",
            )
        )
    else:
        alias.brand_id = brand.id
        alias.alias = name
        alias.status = status
        alias.source = "dictionary"


def _approve(db: Session, key: str, name: str, target_key: str, target_name: str) -> str:
    brand = _upsert_brand(db, target_key, target_name)
    _upsert_alias(db, brand, key, name, "approved")
    db.execute(delete(InvalidBrand).where(InvalidBrand.brand_key == key))
    return "alias" if target_key != key else "approved"


def selected_approvals(payload: dict) -> list[dict]:
    """Validate a batch of approvals. Raises ValueError with a short message."""
    if str(payload.get("action") or "").strip() != "approve_selected":
        raise ValueError("ação desconhecida")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("marque ao menos uma marca")
    if len(items) > 200:
        raise ValueError("muitos itens de uma vez")
    seen: set[str] = set()
    chosen: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("item inválido")
        action = normalize_action(
            {"action": "approve", "key": item.get("key"), "name": item.get("name")}
        )
        if action["key"] in seen:
            continue
        seen.add(action["key"])
        chosen.append(action)
    if not chosen:
        raise ValueError("marque ao menos uma marca")
    return chosen


def apply_brand_action(db: Session, payload: dict) -> dict:
    action = normalize_action(payload)
    key = action["key"]
    name = action["name"]
    if action["action"] == "block":
        if db.scalar(select(InvalidBrand).where(InvalidBrand.brand_key == key)) is None:
            db.add(InvalidBrand(brand_key=key, name=name, reason="bloqueada no dicionário"))
        alias = db.scalar(select(BrandAlias).where(BrandAlias.alias_key == key))
        if alias is not None:
            alias.status = "blocked"
        status = "blocked"
    else:
        target_key = action["target_key"] if action["action"] == "alias" else key
        target_name = action["target_name"] if action["action"] == "alias" else name
        status = _approve(db, key, name, target_key, target_name)
    db.commit()
    return {"ok": True, "key": key, "action": action["action"], "status": status}


def approve_selected(db: Session, payload: dict) -> dict:
    """Approve every checked brand in one commit. Does not rewrite canonical rows."""
    items = selected_approvals(payload)
    for item in items:
        _approve(db, item["key"], item["name"], item["key"], item["name"])
    db.commit()
    return {"ok": True, "action": "approve_selected", "approved": len(items)}
