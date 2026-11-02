"""Telas da lista canônica (server-rendered, sem LLM).

Duas páginas:
- ``/canonical``          — uma linha por produto canônico (ofertas, redes, faixa)
- ``/canonical/{key}``    — todas as ofertas daquele produto, da mais barata

Tudo vem de ``store_listings`` já projetado; nenhum join em tempo de leitura.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from app.catalog.taxonomy import CANONICAL_DEPARTMENTS

_GROUPS = {
    "A1": "A1 · mesma chave em 2+ redes",
    "A2": "A2 · identidade completa",
    "B1": "B1 · marca inferida",
    "B2": "B2 · tamanho ambíguo",
    "B3": "B3 · sem tamanho",
    "B4": "B4 · sem marca",
    "C": "C · sem identidade",
    "R": "R · revisão",
}


def _brl(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _unit_price(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    return f"{_brl(value)}/{unit}" if unit != "un" else f"{_brl(value)}/un"


def _quantity(value: Any) -> str:
    """200.000 -> '200'; 1500.000 -> '1.500'."""
    if value is None:
        return "—"
    number = float(value)
    if number == int(number):
        return f"{int(number):,}".replace(",", ".")
    return f"{number:,.3f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>{escape(title)}</title>
<link rel="stylesheet" href="/static/catalog.css?v=20261016-1"></head>
<body><header class="topbar"><div class="shell brandbar">
<a class="brand" href="/"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<nav class="topnav"><a href="/">Início</a><a href="/catalog">Catálogo</a>
<a href="/canonical">Lista canônica</a><a href="/shopping-lists">Lista de compras</a>
<a href="/catalog/updates">Atualizações</a></nav>
<span class="live"><i></i> Monitoramento ativo</span></div></header>
<main class="shell">{body}</main></body></html>"""


def render_canonical_list(
    *,
    stats: dict[str, Any],
    results: list[dict[str, Any]],
    total_results: int,
    page: int,
    page_size: int,
    product: str | None,
    department: str | None,
    only_covered: bool,
) -> str:
    rows = []
    for item in results:
        key = quote(item["identity_key"], safe="")
        spread = item["spread_percent"]
        spread_label = (
            f"{spread:+.1f}%".replace(".", ",") if spread is not None else "—"
        )
        rows.append(
            f'<tr><td><a href="/canonical/{key}"><strong>{escape(item["canonical_name"])}</strong></a>'
            f'<small class="muted" style="display:block;font-size:11px">'
            f'{escape(item["coverage_group"] or "—")}</small></td>'
            f'<td><span class="pill">{escape(item["department"])}</span></td>'
            f"<td>{item['offers']}</td><td>{item['retailers']}</td>"
            f'<td class="price">{_unit_price(item["min_unit_price"], item["unit"])}</td>'
            f'<td class="price">{_unit_price(item["max_unit_price"], item["unit"])}</td>'
            f'<td><span class="change {"decrease" if (spread or 0) > 0 else "stable"}">'
            f"{spread_label}</span></td></tr>"
        )
    empty = (
        '<tr class="empty"><td colspan="7"><div class="empty-state">'
        "<strong>Nenhum produto canônico com esses filtros</strong>"
        "<p>Rode o backfill canônico ou remova um filtro.</p></div></td></tr>"
    )
    pages = max(1, (total_results + page_size - 1) // page_size)

    def page_url(target: int) -> str:
        params = [f"page={target}", f"size={page_size}"]
        if product:
            params.append(f"product={quote(product)}")
        if department:
            params.append(f"department={quote(department)}")
        if only_covered:
            params.append("covered=1")
        return "/canonical?" + "&".join(params)

    pager = "".join(
        f'<a class="{"active" if target == page else ""}" href="{page_url(target)}">{target}</a>'
        for target in range(max(1, page - 2), min(pages, page + 2) + 1)
    )
    options = "".join(
        f'<option value="{escape(value)}"{" selected" if value == department else ""}>'
        f"{escape(value)}</option>"
        for value in CANONICAL_DEPARTMENTS
    )
    groups = "".join(
        f'<li><span>{escape(_GROUPS.get(group, group))}</span>'
        f"<strong>{count:,} / {stats['priced_by_group'].get(group, 0):,}</strong></li>".replace(
            ",", "."
        )
        for group, count in sorted(stats["by_group"].items())
    )
    body = f"""
<section class="hero"><div><span class="eyebrow">Identidade canônica</span>
<h1>Lista canônica</h1>
<p>O mesmo produto entre redes, comparado por preço unitário (kg, L ou unidade).
Só regras — sem LLM.</p></div></section>
<section class="metrics" aria-label="Cobertura canônica">
<article><span>Produtos canônicos</span><strong>{total_results:,}</strong>
<small>com identidade resolvida</small></article>
<article><span>Comparáveis (A1+A2)</span>
<strong>{stats["listings_comparable"]:,}</strong>
<small>listings em grupos confiáveis</small></article>
<article><span>Com preço unitário</span>
<strong>{stats["listings_with_unit_price"]:,}</strong>
<small>{stats["coverage_percent"]}% dos preços ativos</small></article>
</section>
<details class="addsec"><summary><strong>Cobertura por grupo</strong>
<small class="muted"> (listings / com preço unitário)</small></summary>
<ul style="list-style:none;padding:0;margin:8px 0;display:grid;gap:4px">{groups}</ul></details>
<form class="tools" method="get" action="/canonical">
<div class="review-search"><input type="search" name="product" placeholder="Buscar produto canônico" value="{escape(product or "")}"></div>
<select name="department"><option value="">Todos os departamentos</option>{options}</select>
<label class="hint"><input type="checkbox" name="covered" value="1"{" checked" if only_covered else ""}> só comparáveis (A1/A2)</label>
<button type="submit">Filtrar</button></form>
<table class="sli-table"><thead><tr>
<th>Produto canônico</th><th>Departamento</th><th>Ofertas</th><th>Redes</th>
<th>Menor unitário</th><th>Maior unitário</th><th>Diferença</th>
</tr></thead><tbody>{"".join(rows) or empty}</tbody></table>
<nav class="pager" aria-label="Paginação">{pager}</nav>
"""
    return _shell("Lista canônica", body)


def render_canonical_detail(data: dict[str, Any]) -> str:
    offers = data["offers"]
    cheapest = next((offer for offer in offers if offer["unit_price"] is not None), None)
    rows = []
    for index, offer in enumerate(offers):
        marker = ' style="background:#eef7f2"' if cheapest and offer is cheapest else ""
        rows.append(
            f"<tr{marker}><td>{index + 1}º</td>"
            f'<td><strong>{escape(offer["retailer"] or "")}</strong>'
            f'<small class="muted" style="display:block;font-size:11px">'
            f'{escape(offer["store"] or "")}</small></td>'
            f'<td>{escape(offer["product_name"] or "")}</td>'
            f'<td class="price">{_brl(float(offer["price"]) if offer["price"] is not None else None)}</td>'
            f'<td class="price"><strong>{_unit_price(offer["unit_price"], offer["unit"])}</strong></td>'
            f'<td>{escape(_quantity(offer["comparison_quantity"]))}/{escape(offer["base_unit"] or "—")}</td>'
            f'<td>{escape(offer["coverage_group"] or "—")}</td>'
            f'<td>{"oferta" if offer["is_offer"] else "preço final"}</td></tr>'
        )
    head = (
        f'<section class="hero"><div><span class="eyebrow">Produto canônico</span>'
        f'<h1>{escape(data["canonical_name"])}</h1>'
        f'<p>{escape(data["department"] or "—")} · grupo '
        f'{escape(data["coverage_group"] or "—")} · '
        f'{len(offers)} oferta(s) · comparado por '
        f'{escape(data["comparison_unit"] or "—")}</p></div></section>'
    )
    best = (
        f'<section class="metrics"><article><span>Menor preço unitário</span>'
        f'<strong>{_unit_price(cheapest["unit_price"], cheapest["unit"])}</strong>'
        f'<small>{escape(cheapest["retailer"] or "")} · {escape(cheapest["store"] or "")}</small>'
        f"</article></section>"
        if cheapest
        else ""
    )
    table = (
        '<table class="sli-table"><thead><tr><th>#</th><th>Rede / loja</th>'
        "<th>Nome no varejista</th><th>Preço</th><th>Preço unitário</th>"
        "<th>Conteúdo</th><th>Grupo</th><th>Condição</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
        if rows
        else '<div class="empty">Sem ofertas ativas para este produto.</div>'
    )
    body = f'{head}{best}{table}<p class="hint"><a href="/canonical">← voltar para a lista canônica</a></p>'
    return _shell(data["canonical_name"] or "Produto canônico", body)
