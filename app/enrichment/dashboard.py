"""Server-rendered Açougue comparison dashboard."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

RETAILER_ORDER = (
    "arena-atacado", "goodbom", "atacadao", "savegnago", "davitta",
    "assai", "tenda", "sao-vicente", "max-atacadista",
)

RETAILER_LABELS = {
    "arena-atacado": "Arena",
    "goodbom": "GoodBom",
    "atacadao": "Atacadão",
    "savegnago": "Savegnago",
    "davitta": "Davitta",
    "assai": "Assaí",
    "tenda": "Tenda",
    "sao-vicente": "São Vicente",
    "max-atacadista": "Max",
}


def _brl(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _attr_text(group: dict[str, Any]) -> str:
    parts: list[str] = []
    if group.get("bone_state") == "sem_osso":
        parts.append("sem osso")
    elif group.get("bone_state") == "com_osso":
        parts.append("com osso")
    if group.get("skin_state") == "com_pele":
        parts.append("com pele")
    if group.get("presentation"):
        parts.append(str(group["presentation"]))
    if group.get("conservation"):
        parts.append(str(group["conservation"]))
    if group.get("seasoned"):
        parts.append("temperado")
    return " · ".join(parts)


def _row_html(group: dict[str, Any]) -> str:
    sources = group["sources"]
    prices = [sources.get(slug, {}).get("price_kg") for slug in RETAILER_ORDER]
    present = [p for p in prices if p is not None]
    cheapest = min(present) if present else None
    cells = []
    for slug, price in zip(RETAILER_ORDER, prices, strict=True):
        if price is None:
            cells.append('<td class="na">—</td>')
            continue
        cls = "best" if price == cheapest else ""
        sample = escape(sources[slug].get("sample") or "")
        cells.append(f'<td class="{cls}" title="{sample}">{_brl(price)}</td>')
    n_sources = sum(1 for p in present)
    subtitle = escape(_attr_text(group)) if _attr_text(group) else ""
    search = escape((group["label"] + " " + subtitle).lower())
    sub_html = f'<span class="muted">{subtitle}</span>' if subtitle else ""
    return (
        f'<tr class="pr" data-sources="{n_sources}" data-search="{search}">'
        f'<td class="cut"><strong>{escape(group["label"])}</strong>{sub_html}</td>'
        + "".join(cells)
        + "</tr>"
    )


def render_butcher_dashboard(result: dict[str, Any]) -> str:
    groups = result["groups"]
    llm_info = result.get("llm") or {}
    headers = "".join(
        f"<th>{escape(RETAILER_LABELS.get(slug, slug))}</th>" for slug in RETAILER_ORDER
    )

    # group rows by LLM category (they are already split by form/apresentação)
    categories: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        category = (group.get("llm_category") or "").strip() or "Sem categoria"
        categories.setdefault(category, []).append(group)

    sections: list[str] = []
    for category, members in categories.items():
        rows = "".join(_row_html(g) for g in members)
        header = f"<h3>{escape(category)}</h3>"
        badge = (
            f'<span class="cat-meta">{len(members)} forma(s) · '
            f'<span class="cat-min">a partir de {_brl(min(_min_of(g) for g in members))}</span></span>'
        )
        sections.append(
            f'<details class="cat" data-name="{escape(category.lower())}" open>'
            f"<summary><div class='cat-head'>{header}{badge}</div>"
            '<span class="fam-chev">▾</span></summary>'
            '<div class="table-wrap"><table><thead><tr>'
            f"<th>Corte / forma</th>{headers}</tr></thead>"
            f"<tbody>{rows}</tbody></table></div></details>"
        )
    empty = (
        '<div class="review-empty">Nenhum corte comparável encontrado'
        + (" para os itens aprovados pela LLM." if llm_info.get("llm_active") else ".")
        + "</div>"
    )
    content = "".join(sections) or empty

    llm_strip = ""
    if llm_info.get("llm_active"):
        llm_strip = (
            '<div class="llm-strip">'
            "<span>🛰️ Comparando apenas itens <strong>aprovados pela LLM</strong> "
            f"({llm_info.get('accepted_products', 0)} produtos): os falsos positivos "
            "ficam de fora da aferição.</span>"
            '<span style="margin-left:auto"><a href="/catalog/cuts?all=1" '
            'style="color:#175cd3">Ver sem filtro LLM →</a></span>'
            "</div>"
        )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Açougue — preço por kg</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.cut .muted{{display:block;font-size:12px;color:#607080;font-weight:400}}
td.na{{color:#b0b8c0}}td.best{{background:#e3f6e9;font-weight:700;color:#067647}}
.cat{{background:#fff;border:1px solid var(--line);border-radius:16px;margin-bottom:12px;overflow:hidden;box-shadow:0 3px 12px rgba(20,50,38,.03)}}
.cat>summary{{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:12px 16px;user-select:none}}
.cat>summary::-webkit-details-marker{{display:none}}
.cat[open]>summary{{border-bottom:1px solid var(--line);background:#f7fbf9}}
.cat-head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;min-width:0}}
.cat-head h3{{margin:0;font-size:17px;color:var(--green)}}
.cat-meta{{font-size:12px;color:var(--muted)}}
.cat-min{{color:#067647;font-weight:700}}
.cat .fam-chev{{margin-left:auto;color:#9aa39f;font-size:14px}}
.table-wrap{{overflow-x:auto}}
.cat table{{min-width:900px;border-collapse:collapse;width:100%}}
.cat th{{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);text-align:left;padding:9px 14px;background:#fafcfb;border-bottom:1px solid var(--line)}}
.cat td{{padding:8px 14px;border-bottom:1px solid #eef2f0;font-size:13px;white-space:nowrap}}
.cat tr:last-child td{{border-bottom:0}}
.cat td:first-child{{white-space:normal;min-width:220px}}
.price-tools{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;margin-bottom:16px}}
.review-search{{flex:1 1 240px;display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px;background:#fff}}
.review-search input{{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;color:var(--ink);background:transparent}}
.review-toggle{{display:inline-flex;gap:7px;align-items:center;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;font-size:13px;font-weight:600;cursor:pointer}}
.review-toggle input{{accent-color:var(--green)}}
.review-count{{margin-left:auto;font-size:13px;color:var(--muted);white-space:nowrap}}
.review-empty{{background:var(--surface);border:1px dashed var(--line);border-radius:16px;padding:34px;text-align:center;color:var(--muted)}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Açougue</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões do Açougue">
<a class="active" href="/catalog/cuts">Comparativo R$/kg</a>
<a href="/catalog/butcher-review">Revisão de classificação</a>
<a href="/catalog/categories">Categorias</a>
</nav>
<section class="hero"><div><span class="eyebrow">Aferição de preços · LLM</span>
<h1>Açougue — preço por kg</h1>
<p>{result['total_groups']} formas comparáveis a partir de {result['total_items']} itens, agrupadas por categoria. Cada linha é uma FORMA (Peça/Kg/Fatiado/Cubos/Moída…): compare sempre a mesma forma entre redes — o menor R$/kg de cada linha está destacado.</p></div></section>
{llm_strip}
<div class="price-tools">
<div class="review-search">
<input id="q" type="search" placeholder="Filtrar por categoria, corte ou forma…" autocomplete="off">
</div>
<label class="review-toggle"><input id="only-assoc" type="checkbox"> Só com ≥2 fontes</label>
<span class="review-count" id="count"></span>
<button class="page-button" id="expand" type="button" style="background:var(--mint)">Expandir</button>
<button class="page-button" id="collapse" type="button" style="background:var(--mint)">Recolher</button>
</div>
<div id="cats">{content}</div>
</main>
<script>
(function(){{
  const root=document.getElementById('cats');
  const q=document.getElementById('q');
  const onlyAssoc=document.getElementById('only-assoc');
  const count=document.getElementById('count');
  const cats=[...root.querySelectorAll('.cat')];
  function apply(){{
    const term=q.value.trim().toLowerCase();
    let shown=0;
    for(const cat of cats){{
      const catName=(cat.dataset.name||'');
      let any=false;
      for(const row of cat.querySelectorAll('tr.pr')){{
        const text=(row.dataset.search||'')+' '+catName;
        const okText=!term||text.includes(term);
        const okSrc=!onlyAssoc.checked||Number(row.dataset.sources||0)>=2;
        const show=okText&&okSrc;
        row.style.display=show?'':'none';
        if(show)any=true;
      }}
      cat.style.display=any?'':'none';
      if(any)shown++;
    }}
    count.textContent=shown+' de '+cats.length+' categorias';
  }}
  q.addEventListener('input',apply);
  onlyAssoc.addEventListener('change',apply);
  document.getElementById('expand').addEventListener('click',function(){{cats.forEach(c=>c.open=true);}});
  document.getElementById('collapse').addEventListener('click',function(){{cats.forEach(c=>c.open=false);}});
  apply();
}})();
</script>
</body></html>"""


def _min_of(group: dict[str, Any]) -> Decimal:
    values = [
        info["price_kg"]
        for info in group["sources"].values()
        if info.get("price_kg") is not None
    ]
    return min(values) if values else Decimal("0")
