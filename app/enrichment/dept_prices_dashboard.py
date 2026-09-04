"""Server-rendered per-department price comparison screen (R$ per unit)."""

from __future__ import annotations

from html import escape
from typing import Any

from app.enrichment.dashboard import RETAILER_LABELS


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _dept_select(department: str) -> str:
    from app.catalog.taxonomy import CANONICAL_DEPARTMENTS

    options = "".join(
        f'<option value="{escape(d)}"{" selected" if d == department else ""}>'
        f"{escape(d)}</option>"
        for d in CANONICAL_DEPARTMENTS
    )
    return (
        "<span class='deptsel'><label>Departamento</label>"
        "<select onchange=\"location.href='/catalog/dept-prices?department='"
        "+encodeURIComponent(this.value)\" title='Trocar departamento'>"
        f"{options}</select></span>"
    )


def render_dept_prices_page(payload: dict[str, Any]) -> str:
    department = payload["department"]
    groups = payload["groups"]

    rows: list[str] = []
    for group in groups:
        sources = group["sources"]
        cheapest = sources[0] if sources else None
        sources_html = []
        for i, source in enumerate(sources):
            price = _brl(source["price"])
            is_best = i == 0
            detail = " · ".join(
                part
                for part in (
                    RETAILER_LABELS.get(source["slug"], source["slug"]),
                    source["store"] or "",
                    source["sample"] or "",
                )
                if part
            )
            sources_html.append(
                "<li" + (" class='best'" if is_best else "") + ">"
                + ("<b>✓ mais barato:</b> " if is_best else "")
                + f"<span class='p'>{price}/{escape(group['unit'])}</span>"
                + f"<span class='d'>{escape(detail)}</span></li>"
            )
        cheapest_line = (
            f"{_brl(cheapest['price'])}/{escape(group['unit'])}"
            f" · {escape(RETAILER_LABELS.get(cheapest['slug'], cheapest['slug']))}"
            if cheapest
            else "—"
        )
        rows.append(
            "<details class='pr-row'><summary>"
            "<span class='cat'>" + escape(group["canonical"]) + "</span>"
            "<span class='u'>" + escape(group["unit"]) + "</span>"
            f"<span class='n'>{group['products']} prod.</span>"
            f"<span class='best'>{escape(cheapest_line)}</span>"
            "</summary><ul class='srcs'>" + "".join(sources_html) + "</ul></details>"
        )

    body = "".join(rows) or (
        "<div class='empty'>Nenhuma categoria com preço por unidade neste "
        "departamento (ou nada classificado ainda).</div>"
    )

    chips = (
        "<div class='tools'>"
        + _dept_select(department)
        + f"<span class='chip-stat'><b>{_num(len(groups))}</b> categorias c/ preço</span>"
        + f"<span class='chip-stat'><b>{_num(payload['priced_products'])}</b> produtos precificados</span>"
        + f"<span class='chip-stat'><b>{_num(payload['unparsed_products'])}</b> sem unidade</span>"
        + "</div>"
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>{escape(department)} — comparativo de preços</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.tools{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}}
.deptsel{{display:flex;gap:8px;align-items:center;margin-right:4px}}
.deptsel label{{font-size:12px;color:var(--muted);font-weight:700;white-space:nowrap}}
.deptsel select{{padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px;background:#fff}}
.chip-stat{{font-size:13px;color:var(--muted)}}.chip-stat b{{font-size:17px;color:var(--green);display:block}}
.sbox{{flex:1 1 260px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px;background:#fff}}
.sbox input{{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;background:transparent}}
.pr-row{{background:#fff;border:1px solid var(--line);border-radius:14px;margin-bottom:8px;overflow:hidden}}
.pr-row>summary{{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 14px}}
.pr-row>summary::-webkit-details-marker{{display:none}}
.pr-row>summary:hover{{background:#fbfdfc}}
.pr-row[open]>summary{{border-bottom:1px solid var(--line)}}
.pr-row .cat{{font-weight:700;font-size:14.5px;flex:1 1 180px}}
.pr-row .u{{font-size:11px;color:var(--green);background:#eef6f1;border-radius:99px;padding:2px 8px;font-weight:800}}
.pr-row .n{{font-size:12px;color:var(--muted)}}
.pr-row .best{{font-size:13px;color:#067647;font-weight:800;white-space:nowrap}}
ul.srcs{{list-style:none;margin:0;padding:8px 14px 12px}}
ul.srcs li{{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;padding:4px 0;font-size:13px}}
ul.srcs li .p{{font-weight:800;color:var(--green);min-width:120px}}
ul.srcs li .d{{color:#51615a;font-size:12px}}
ul.srcs li.best{{background:#eaf9f1;border-radius:8px;padding:6px 8px;margin-left:-8px}}
.empty{{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted)}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> {escape(department)}</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões">
<a class="active" href="/catalog/dept-prices?department={escape(department)}">Comparativo de preços</a>
<a href="/catalog/butcher-review?department={escape(department)}">Revisão</a>
<a href="/catalog/categories?department={escape(department)}">Categorias</a>
<a href="/shopping-lists">Lista</a>
</nav>
<section class="hero"><div><span class="eyebrow">Aferição de preços · por unidade</span>
<h1>Comparativo — {escape(department)}</h1>
<p>Produtos classificados agrupados por categoria canônica, com o melhor preço
<b>por unidade</b> (R$/kg, R$/L ou R$/un) em cada rede. O menor de cada categoria
está destacado — expanda para ver loja e o produto que gerou o preço.</p></div></section>
{chips}
<div class="tools">
<div class="sbox"><input id="q" type="search" placeholder="Filtrar categoria…"></div>
</div>
<div id="list">{body}</div>
</main>
<script>
(function(){{
  const q=document.getElementById('q');
  const rows=[...document.querySelectorAll('#list details.pr-row')];
  q.addEventListener('input',function(){{
    const t=q.value.trim().toLowerCase();
    for(const r of rows) r.style.display=(!t||(r.textContent||'').toLowerCase().includes(t))?'':'none';
  }});
}})();
</script>
</body></html>"""
