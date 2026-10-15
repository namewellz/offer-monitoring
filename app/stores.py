"""Store metadata: filtros (rede/cidade/bairro/tipo/region), rotulos de exibicao.

Filtros chegam pela query string de qualquer pagina/JSON e sao guardados num
ContextVar (middleware em ``app.main``); ``apply_store_filter`` aplica nas
consultas de listings do v2. Padrao: lojas ``region_bucket='fora'`` ficam ocultas.
CEP nunca e exposto aqui.
"""

from __future__ import annotations

import json
import time
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

FILTER_PARAMS = ("rede", "cidade", "bairro", "tipo", "region")


@dataclass(frozen=True)
class StoreFilter:
    rede: tuple[str, ...] = ()
    cidade: tuple[str, ...] = ()
    bairro: tuple[str, ...] = ()
    tipo: tuple[str, ...] = ()
    region: tuple[str, ...] = ()  # vazio => padrao (oculta 'fora'); 'all' => tudo

    @property
    def key(self) -> str:
        return "|".join(",".join(getattr(self, name)) for name in FILTER_PARAMS)

    @classmethod
    def from_params(cls, params: Any) -> "StoreFilter":
        values = {}
        for name in FILTER_PARAMS:
            raw = params.get(name) if params is not None else None
            parts = [p.strip() for p in str(raw or "").split(",") if p.strip()]
            values[name] = tuple(sorted(fold(p) for p in parts))
        return cls(**values)


CURRENT_FILTER: ContextVar[StoreFilter] = ContextVar("store_filter", default=StoreFilter())


def fold(value: str | None) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text_value if not unicodedata.combining(c)).casefold().strip()


def _folded(column):
    return func.lower(func.translate(column, "ÁÀÂÃÄáàâãäÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÕÖóòôõöÚÙÛÜúùûüÇç",
                                     "AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCc"))


def apply_store_filter(query, store_model, retailer_model, flt: StoreFilter | None = None):
    flt = flt or CURRENT_FILTER.get()
    if flt.region and "all" not in flt.region:
        query = query.where(store_model.region_bucket.in_(flt.region))
    elif not flt.region:
        query = query.where(
            or_(store_model.region_bucket.is_(None), store_model.region_bucket != "fora")
        )
    if flt.rede:
        query = query.where(
            or_(_folded(retailer_model.slug).in_(flt.rede), _folded(retailer_model.name).in_(flt.rede))
        )
    if flt.cidade:
        query = query.where(_folded(store_model.city).in_(flt.cidade))
    if flt.bairro:
        query = query.where(_folded(store_model.neighborhood).in_(flt.bairro))
    if flt.tipo:
        query = query.where(store_model.store_type.in_(flt.tipo))
    return query


def store_label(store_model):
    """SQL expression: display_name with fallback to the raw name."""
    return func.coalesce(store_model.display_name, store_model.name)


def list_stores(db: Session, flt: StoreFilter | None = None) -> list[dict[str, Any]]:
    from app.db.models import Retailer, Store

    query = select(Store, Retailer).join(Retailer, Retailer.id == Store.retailer_id).where(
        Store.active.is_(True)
    )
    query = apply_store_filter(query, Store, Retailer, flt)
    rows = db.execute(query.order_by(Retailer.name, Store.city, Store.neighborhood)).all()
    return [
        {
            "id": str(store.id),
            "rede": retailer.name,
            "retailer_slug": retailer.slug,
            "cidade": store.city,
            "bairro": store.neighborhood,
            "tipo": store.store_type,
            "store_code": store.store_code,
            "region": store.region_bucket,
            "display_name": store.display_name or store.name,
            "short_label": store.short_label or store.name,
            "curation": (store.field_sources or {}).get("curation"),
        }
        for store, retailer in rows
    ]


def refresh_store_labels(db: Session) -> int:
    count = db.execute(text("SELECT refresh_store_labels()")).scalar() or 0
    db.commit()
    _LABELS["ts"] = 0.0
    return int(count)


_LABELS: dict[str, Any] = {"ts": 0.0, "map": {}}


def label_map(db: Session) -> dict[str, str]:
    """display_name -> short_label (cached 5 min) for the mobile label swap."""
    if time.time() - _LABELS["ts"] > 300:
        from app.db.models import Store

        rows = db.execute(
            select(Store.display_name, Store.short_label).where(
                Store.display_name.is_not(None), Store.active.is_(True)
            )
        ).all()
        _LABELS["map"] = {d: s for d, s in rows if d and s and d != s}
        _LABELS["ts"] = time.time()
    return _LABELS["map"]


def label_assets(db: Session) -> str:
    """CSS+JS injected into HTML pages: on narrow screens show short_label."""
    mapping = json.dumps(label_map(db), ensure_ascii=False).replace("</", "<\\/")
    return (
        "<script>(function(){var M=" + mapping + ";"
        "var K=Object.keys(M).sort(function(a,b){return b.length-a.length});"
        "if(!K.length)return;var mq=window.matchMedia('(max-width: 700px)');"
        "function sw(root){if(!mq.matches||!root)return;"
        "var w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null),n;"
        "while((n=w.nextNode())){var t=n.nodeValue,o=t;"
        "for(var i=0;i<K.length;i++){if(t.indexOf(K[i])>-1)t=t.split(K[i]).join(M[K[i]]);}"
        "if(t!==o)n.nodeValue=t;}}"
        "function run(){sw(document.body);new MutationObserver(function(ms){"
        "ms.forEach(function(m){m.addedNodes.forEach(function(x){"
        "sw(x.nodeType===3?x.parentNode:x)})})}).observe(document.body,{childList:true,subtree:true});}"
        "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run);else run();"
        "})();</script>"
    )
