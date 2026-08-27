from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import urlencode

from app.catalog.taxonomy import CANONICAL_DEPARTMENTS

RETAILERS = (
    ("arena-atacado", "Arena Atacado"),
    ("goodbom", "GoodBom"),
    ("atacadao", "Atacadão"),
    ("savegnago", "Savegnago"),
    ("davitta", "Davitta"),
    ("assai", "Assaí"),
    ("tenda", "Tenda Atacado"),
    ("sao-vicente", "São Vicente"),
)


def _money(value: Any) -> str:
    if value is None:
        return "—"
    return f"R$ {float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _options(values, selected: str | None) -> str:
    return "".join(
        f'<option value="{escape(value)}" {"selected" if selected == value else ""}>'
        f"{escape(label)}</option>"
        for value, label in values
    )


def render_catalog_dashboard(
    *,
    results: list[dict[str, Any]],
    product: str | None,
    retailer: str | None,
    department: str | None,
    direction: str,
    minimum_percent: float,
    view: str,
    total_results: int,
    page: int,
    page_size: int,
    latest_runs: list[dict[str, Any]],
) -> str:
    rows = []
    for result in results:
        raw_percent = result["change_percent"]
        percent = float(raw_percent) if raw_percent is not None else None
        regular_price = result.get("regular_price")
        current_price = result["current_price"]
        offer_percent = (
            (float(regular_price) - float(current_price)) / float(regular_price) * 100
            if view == "offers"
            and regular_price is not None
            and current_price is not None
            and float(regular_price) > float(current_price)
            and float(regular_price) > 0
            else None
        )
        css_class = (
            "increase"
            if percent is not None and percent > 0
            else "decrease"
            if percent is not None and percent < 0
            else "stable"
        )
        variation = (
            f"Oferta -{offer_percent:.2f}%"
            if view == "offers" and offer_percent is not None
            else "Preço especial"
            if view == "offers"
            else
            f"↑ {percent:+.2f}%"
            if percent is not None and percent > 0
            else f"↓ {percent:+.2f}%"
            if percent is not None and percent < 0
            else "Sem alteração"
            if percent == 0
            else "Sem referência"
        )
        previous_value = regular_price if view == "offers" else result["previous_price"]
        previous_sort = previous_value if previous_value is not None else ""
        current_sort = result["current_price"] if result["current_price"] is not None else ""
        store = result["store"] or "Todas as lojas"
        observed = result["observed_at"]
        rows.append(
            f'<tr data-product="{escape(result["product"].casefold())}" '
            f'data-retailer="{escape(result["retailer"].casefold())}" '
            f'data-department="{escape(result["department"].casefold())}" '
            f'data-store="{escape(store.casefold())}" '
            f'data-previous="{previous_sort}" data-current="{current_sort}" '
            f'data-change="{offer_percent if view == "offers" and offer_percent is not None else percent if percent is not None else ""}" '
            f'data-condition="{escape(result["price_condition_type"])}" '
            f'data-observed="{observed.isoformat()}">'
            f'<td data-label="Produto"><strong>{escape(result["product"])}</strong>'
            f'<span class="muted product-meta">{escape(result.get("brand") or "Marca não informada")}</span></td>'
            f'<td data-label="Departamento"><span class="pill">{escape(result["department"])}</span></td>'
            f'<td data-label="Supermercado">{escape(result["retailer"])}</td>'
            f'<td data-label="Loja">{escape(store)}</td>'
            f'<td data-label="{"Preço de" if view == "offers" else "Preço anterior"}">{_money(previous_value)}</td>'
            f'<td data-label="Preço atual"><strong>{_money(result["current_price"])}</strong></td>'
            f'<td data-label="Condição" class="condition">{escape(result["price_condition"])}</td>'
            f'<td data-label="Variação"><span class="change {css_class}">{variation}</span></td>'
            f'<td data-label="Coleta"><time datetime="{observed.isoformat()}">{observed.strftime("%d/%m/%Y %H:%M")}</time></td>'
            "</tr>"
        )

    empty = (
        '<tr class="empty"><td colspan="9"><div class="empty-state">'
        '<span class="empty-icon">✓</span><strong>Nenhum produto encontrado</strong>'
        '<p>Tente mudar a busca ou remover um dos filtros aplicados.</p>'
        "</div></td></tr>"
    )
    department_values = [(value, value) for value in CANONICAL_DEPARTMENTS]
    last_collected: datetime | None = max(
        (run["collected_at"] for run in latest_runs), default=None
    )
    total_products = sum(int(run["product_count"] or 0) for run in latest_runs)
    active_retailers = len(latest_runs)
    result_kind = {
        "all": "produto(s)",
        "offers": "oferta(s)",
        "changes": "alteração(ões)",
    }[view]
    result_description = {
        "all": "produto(s) na coleta mais recente de cada loja",
        "offers": "oferta(s) vigente(s) na coleta mais recente de cada loja",
        "changes": "alteração(ões) na coleta mais recente de cada loja",
    }[view]
    previous_heading = "Preço de" if view == "offers" else "Anterior"
    variation_heading = "Desconto" if view == "offers" else "Variação"
    total_pages = max(1, (total_results + page_size - 1) // page_size)
    first_result = (page - 1) * page_size + 1 if total_results else 0
    last_result = min(page * page_size, total_results)
    total_results_label = f"{total_results:,}".replace(",", ".")
    first_result_label = f"{first_result:,}".replace(",", ".")
    last_result_label = f"{last_result:,}".replace(",", ".")

    def page_url(target: int) -> str:
        parameters = {
            "product": product or "",
            "retailer": retailer or "",
            "department": department or "",
            "direction": direction,
            "minimum_percent": f"{minimum_percent:g}",
            "view": view,
            "page": target,
        }
        return "/catalog?" + escape(urlencode(parameters), quote=True)

    pagination = ""
    if total_pages > 1:
        previous = (
            f'<a class="page-button" href="{page_url(page - 1)}">← Anterior</a>'
            if page > 1
            else '<span class="page-button disabled">← Anterior</span>'
        )
        following = (
            f'<a class="page-button" href="{page_url(page + 1)}">Próxima →</a>'
            if page < total_pages
            else '<span class="page-button disabled">Próxima →</span>'
        )
        pagination = (
            '<nav class="pagination" aria-label="Paginação dos resultados">'
            f"{previous}<span>Página <strong>{page}</strong> de <strong>{total_pages}</strong></span>"
            f"{following}</nav>"
        )
    last_label = last_collected.strftime("%d/%m às %H:%M") if last_collected else "Sem coletas"
    run_items = "".join(
        f'<li><span><strong>{escape(run["retailer"])}</strong>'
        f'<small>{escape(run["store"] or "Catálogo geral")}</small></span>'
        f'<span class="run-count">{int(run["product_count"] or 0):,} itens</span></li>'.replace(",", ".")
        for run in sorted(latest_runs, key=lambda item: item["retailer"])
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Monitor de preços</title>
<link rel="stylesheet" href="/static/catalog.css"></head>
<body><header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Monitoramento ativo</span></div></header>
<main class="shell">
<section class="hero"><div><span class="eyebrow">Inteligência de preços</span>
<h1>Preços dos produtos</h1><p>Consulte todo o catálogo atual ou destaque somente as mudanças de preço.</p></div>
<button class="secondary mobile-refresh" type="button" data-open-update>Atualizar catálogo</button></section>
<nav class="view-tabs" aria-label="Visões do catálogo">
<a href="/catalog?view=all" class="{"active" if view == "all" else ""}">Todos os produtos</a>
<a href="/catalog?view=offers" class="{"active" if view == "offers" else ""}">Em oferta</a>
<a href="/catalog?view=changes" class="{"active" if view == "changes" else ""}">Variações</a>
</nav>
<section class="metrics" aria-label="Resumo do catálogo">
<article><span>Produtos monitorados</span><strong>{total_products:,}</strong><small>nas coletas mais recentes</small></article>
<article><span>Supermercados</span><strong>{active_retailers}</strong><small>fontes com dados ativos</small></article>
<article><span>Resultados encontrados</span><strong>{total_results_label}</strong><small>{result_kind} conforme os filtros</small></article>
<article><span>Última coleta</span><strong class="metric-date">{last_label}</strong><small>histórico preservado</small></article>
</section>
<section class="workspace">
<div class="main-column">
<form class="filters" method="get"><div class="section-heading"><div><h2>Explore os preços</h2>
<p>Busque em todos os produtos ou mostre apenas aqueles que tiveram variação.</p></div><a href="/catalog">Limpar filtros</a></div>
<div class="filter-grid"><label class="search-field"><span>Produto</span>
<input name="product" value="{escape(product or '')}" placeholder="Ex.: arroz, cerveja, sabonete"></label>
<label><span>Exibição</span><select name="view">
<option value="all" {"selected" if view == "all" else ""}>Todos os produtos</option>
<option value="offers" {"selected" if view == "offers" else ""}>Em oferta</option>
<option value="changes" {"selected" if view == "changes" else ""}>Somente variações</option></select></label>
<label><span>Departamento</span><select name="department"><option value="">Todos</option>{_options(department_values, department)}</select></label>
<label><span>Supermercado</span><select name="retailer"><option value="">Todos</option>{_options(RETAILERS, retailer)}</select></label>
<label><span>Movimento</span><select name="direction"><option value="all">Todos</option>
<option value="up" {"selected" if direction == "up" else ""}>Aumentos</option>
<option value="down" {"selected" if direction == "down" else ""}>Reduções</option></select></label>
<label><span>Variação mínima</span><div class="percent-input"><input name="minimum_percent" type="number" min="0" step="0.1" value="{minimum_percent:g}"><b>%</b></div></label>
<button class="primary" type="submit">Aplicar filtros</button></div></form>
<section class="results-card"><div class="results-heading"><div><h2>Resultados</h2>
<p>{total_results_label} {result_description} · exibindo {first_result_label}–{last_result_label}</p></div>
<span class="desktop-hint">Toque nos títulos para ordenar</span></div>
<div class="table-wrap"><table id="catalog-table"><thead><tr>
<th class="sortable" data-key="product">Produto</th><th class="sortable" data-key="department">Departamento</th>
<th class="sortable" data-key="retailer">Supermercado</th><th class="sortable" data-key="store">Loja</th>
<th class="sortable numeric" data-key="previous">{previous_heading}</th><th class="sortable numeric" data-key="current">Atual</th>
<th class="sortable condition" data-key="condition">Condição</th><th class="sortable numeric" data-key="change">{variation_heading}</th>
<th class="sortable" data-key="observed">Coleta</th></tr></thead><tbody>{''.join(rows) or empty}</tbody></table></div>{pagination}</section>
</div><aside class="side-column">
<section class="update-card" id="manual-update"><span class="eyebrow">Controle</span><h2>Atualização manual</h2>
<p>Solicite uma nova coleta sem esperar o próximo horário automático.</p>
<label><span>Supermercado</span><select id="update-retailer">{_options(RETAILERS, "sao-vicente")}</select></label>
<button class="primary full" id="update-button" type="button">Iniciar atualização</button>
<div id="update-status" class="update-status" role="status" aria-live="polite"></div></section>
<section class="sources-card"><div class="section-heading"><div><h2>Últimas fontes</h2><p>Volume da coleta atual</p></div></div>
<ul class="source-list">{run_items or '<li class="muted">Nenhuma coleta disponível.</li>'}</ul></section>
</aside></section></main>
<script src="/static/catalog.js" defer></script></body></html>""".replace(
        f"{total_products:,}", f"{total_products:,}".replace(",", ".")
    )
