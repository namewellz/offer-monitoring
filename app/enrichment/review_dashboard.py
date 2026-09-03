"""Server-rendered Açougue classification review screen.

Shows the families produced by the deterministic parser (species/cut/type +
attributes), each with its member items per retailer and R$/kg, plus counters of
items the parser excluded (non-meat / prepared / plant-based). Filtering is
client-side for instant feedback; data comes from ``app.enrichment.review``.
"""

from __future__ import annotations

from html import escape
from typing import Any

from app.enrichment.dashboard import RETAILER_LABELS

_PAGE_CSS = """
.review-tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--surface);
 border:1px solid var(--line);border-radius:16px;padding:12px;margin-bottom:16px;box-shadow:0 4px 16px rgba(20,50,38,.04)}
.review-search{flex:1 1 260px;display:flex;align-items:center;gap:8px;border:1px solid var(--line);
 border-radius:11px;padding:2px 4px 2px 12px;background:#fff}
.review-search input{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;color:var(--ink);background:transparent}
.review-search .kbd{flex:none;color:#9aa39f;font-size:11px;border:1px solid var(--line);border-radius:6px;padding:3px 6px}
.review-toggle{display:inline-flex;gap:7px;align-items:center;padding:9px 12px;border:1px solid var(--line);
 border-radius:10px;background:#fff;color:var(--ink);font-size:13px;font-weight:600;cursor:pointer}
.review-toggle:hover{border-color:#c8d4ce}
.review-toggle input{accent-color:var(--green)}
.review-count{margin-left:auto;font-size:13px;color:var(--muted);white-space:nowrap}
.review-family{background:var(--surface);border:1px solid var(--line);border-radius:16px;margin-bottom:10px;
 box-shadow:0 3px 12px rgba(20,50,38,.03);overflow:hidden}
.review-family>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:14px;
 padding:14px 16px;user-select:none}
.review-family>summary::-webkit-details-marker{display:none}
.review-family>summary:hover{background:#fbfdfc}
.review-family[open]>summary{border-bottom:1px solid var(--line)}
.fam-chev{margin-left:auto;color:#9aa39f;font-size:18px;flex:none;transition:transform .12s}
.review-family[open] .fam-chev{transform:rotate(90deg)}
.fam-main{min-width:0}
.fam-title{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.fam-title h3{margin:0;font-size:18px;letter-spacing:-.01em}
.fam-attrs{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.chip{display:inline-flex;align-items:center;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:750;
 background:#f1f5f3;color:#51615a;border:1px solid #e3ebe7}
.chip.spec{background:#eaf6f0;color:#145c42}
.chip.type{background:#eef2ff;color:#3a55c8}
.chip.warn{background:#fff4e6;color:#9a6a00}
.fam-meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex:none}
.fam-price{font-weight:800;font-size:13px;color:var(--green)}
.fam-price .dim{color:#9aa39f;font-weight:600}
.fam-src{font-size:11px;color:var(--muted)}
.review-items{overflow-x:auto}
.review-items table{width:100%;border-collapse:collapse;min-width:760px}
.review-items th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
 text-align:left;padding:9px 14px;border-bottom:1px solid var(--line);background:#fafcfb}
.review-items td{padding:8px 14px;border-bottom:1px solid #eef2f0;font-size:13px;vertical-align:top}
.review-items tr:last-child td{border-bottom:0}
td.price{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
td.price.best{font-weight:800;color:#067647;background:#eaf9f1}
td.name{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;color:#33413a}
.review-empty{background:var(--surface);border:1px dashed var(--line);border-radius:16px;padding:34px;
 text-align:center;color:var(--muted)}
.excluded-note{font-size:12.5px;color:var(--muted);line-height:1.5}
.metrics{grid-template-columns:repeat(4,1fr)}
@media(max-width:820px){.metrics{grid-template-columns:repeat(2,1fr)}.fam-meta{display:none}
 .review-items table{min-width:620px}}
"""


def _attr_list(family: dict[str, Any]) -> list[str]:
    return list(family.get("attributes") or [])


def _family_card(family: dict[str, Any]) -> str:
    chips: list[str] = []
    if family.get("species"):
        chips.append(f'<span class="chip spec">{escape(family["species"])}</span>')
    if family.get("cut_type"):
        chips.append(f'<span class="chip type">tipo {escape(family["cut_type"])}</span>')
    for attr in _attr_list(family):
        chips.append(f'<span class="chip">{escape(attr)}</span>')

    # build item rows
    rows: list[str] = []
    for item in family["items"]:
        store = item.get("store") or ""
        price = item.get("price_kg")
        price_cell = "—"
        if price is not None:
            cls = ' class="price best"' if item.get("cheapest") else ' class="price"'
            price_cell = (
                f"<td{cls}>{_brl(price)}</td>"
            )
        else:
            price_cell = '<td class="price">—</td>'
        source = RETAILER_LABELS.get(item["source"], item["source"])
        store_html = f'<span class="muted">{escape(store)}</span>' if store else ""
        rows.append(
            "<tr>"
            f'<td>{escape(source)} {store_html}</td>'
            f'{price_cell}'
            f'<td class="name" title="product_id={item.get("product_id")}">{escape(item["raw_name"])}</td>'
            "</tr>"
        )
    item_table = (
        '<div class="review-items"><table>'
        "<thead><tr><th>Fonte</th><th>R$/kg</th><th>Nome original</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )

    price_range = ""
    low, high = family.get("price_kg_min"), family.get("price_kg_max")
    if low is not None:
        price_range = (
            f'<span class="fam-price">{_brl(low)}'
            f'<span class="dim"> – {_brl(high)}</span></span>'
        )
    src_text = (
        f"{family['source_count']} fonte(s)"
        if family["source_count"] == len(family["sources"])
        else f"{family['source_count']} fonte(s)"
    )

    search_text = " ".join(
        [family["label"] or "", *(item["raw_name"] for item in family["items"])]
    ).lower()

    return (
        f'<details class="review-family" data-search="{escape(search_text)}" '
        f'data-sources="{family["source_count"]}" '
        f'data-items="{family["item_count"]}">'
        "<summary>"
        '<div class="fam-main">'
        f'<div class="fam-title"><h3>{escape(family["label"])}</h3></div>'
        f'<div class="fam-attrs">{"".join(chips)}</div>'
        "</div>"
        '<div class="fam-meta">'
        f"{price_range}"
        f'<span class="fam-src">{family["item_count"]} itens · {src_text}</span>'
        "</div>"
        '<span class="fam-chev">›</span>'
        "</summary>"
        f"{item_table}"
        "</details>"
    )


def _brl(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _metric(value: Any, label: str, hint: str = "") -> str:
    small = f"<small>{escape(hint)}</small>" if hint else ""
    return (
        f"<article><span>{escape(label)}</span>"
        f"<strong>{value}</strong>{small}</article>"
    )


def render_butcher_review(payload: dict[str, Any]) -> str:
    families = payload["families"]
    excluded = payload.get("excluded") or {}
    excluded_total = payload.get("excluded_total") or sum(excluded.values())

    exclusion_detail = " · ".join(
        f"{count} {name.replace('_', ' ')}"
        for name, count in sorted(excluded.items(), key=lambda kv: -kv[1])
    )
    other_depts = payload.get("other_departments", 0)

    family_cards = "".join(_family_card(f) for f in families)
    empty_block = (
        '<div class="review-empty">Nenhuma família corresponde aos filtros.</div>'
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Açougue — revisão de classificação</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>{_PAGE_CSS}</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Açougue</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões do Açougue">
<a href="/catalog/cuts">Comparativo R$/kg</a>
<a class="active" href="/catalog/butcher-review">Revisão de classificação</a>
</nav>
<section class="hero"><div><span class="eyebrow">Motor determinístico · v2</span>
<h1>Revisão do Açougue</h1>
<p>{payload['total_families']} famílias a partir de {payload['total_items']} itens classificados
({payload['scanned_listings']} listagens analisadas). Cada família é um corte agrupado por
espécie/corte/tipo/osso/pele/apresentação/conservação/tempero. Expanda para conferir os itens
por fonte e o R$/kg — o menor de cada família está destacado.</p>
<p class="excluded-note">Nesta tela os dados são lidos ao vivo do catálogo v2
(atualize para refletir nova coleta). Itens cujo nome <strong>menciona carne</strong> mas o parser
excluiu (mercearia com "sabor carne", preparados como hambúrguer/espetinho, vegano, etc.) somam
{excluded_total} e não aparecem nas famílias: {escape(exclusion_detail)}.
Além deles, {other_depts} listagens de outros departamentos (sem referência a corte/espécie)
são ignoradas na revisão.</p>
</div></section>
<div class="metrics">
{_metric(payload['total_families'], 'Famílias')}
{_metric(payload['total_items'], 'Itens classificados')}
{_metric(payload['families_with_associations'], 'Famílias com ≥2 fontes', 'possível comparação entre redes')}
{_metric(excluded_total, 'Excluídos pelo parser', 'não-carne / preparados / vegano')}
</div>
<div class="review-tools">
<div class="review-search">
<input id="q" type="search" placeholder="Filtrar por corte, tipo ou nome do produto…" autocomplete="off">
<span class="kbd">/</span>
</div>
<label class="review-toggle"><input id="only-assoc" type="checkbox"> Só com ≥2 fontes</label>
<label class="review-toggle"><input id="hide-single" type="checkbox"> Ocultar 1 item</label>
<span class="review-count" id="count"></span>
<button class="page-button" id="expand-all" type="button" style="background:var(--mint)">Expandir tudo</button>
</div>
<div id="families">{family_cards or empty_block}</div>
</main>
<script>
(function(){{
  const root=document.getElementById('families');
  const q=document.getElementById('q');
  const onlyAssoc=document.getElementById('only-assoc');
  const hideSingle=document.getElementById('hide-single');
  const count=document.getElementById('count');
  const cards=[...root.querySelectorAll('.review-family')];
  function matches(el){{
    const text=el.dataset.search||'';
    const srcs=Number(el.dataset.sources||1);
    const items=Number(el.dataset.items||1);
    const term=q.value.trim().toLowerCase();
    if(term&&!text.includes(term))return false;
    if(onlyAssoc.checked&&srcs<2)return false;
    if(hideSingle.checked&&items<2)return false;
    return true;
  }}
  function apply(){{
    let n=0;
    for(const el of cards){{
      const show=matches(el);
      el.style.display=show?'':'none';
      if(show)n++;
    }}
    count.textContent=n+' de '+cards.length+' famílias';
  }}
  q.addEventListener('input',apply);
  onlyAssoc.addEventListener('change',apply);
  hideSingle.addEventListener('change',apply);
  document.getElementById('expand-all').addEventListener('click',function(){{
    const all=cards.every(c=>c.open);
    for(const el of cards) if(el.style.display!=='none') el.open=!all;
  }});
  apply();
  document.addEventListener('keydown',function(e){{
    if(e.key==='/'&&document.activeElement!==q){{e.preventDefault();q.focus();}}
  }});
}})();
</script>
</body></html>"""
