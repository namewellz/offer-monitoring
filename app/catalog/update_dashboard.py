from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

STATUS_LABELS = {
    "SUCCESS": "Concluída",
    "FINISHED": "Concluída",
    "PARTIAL_SUCCESS": "Parcial",
    "FAILED": "Falhou",
    "QUEUED": "Na fila",
    "STARTED": "Em andamento",
    "DEFERRED": "Aguardando",
    "SCHEDULED": "Agendada",
    "STOPPED": "Interrompida",
    "CANCELED": "Cancelada",
}


def _number(value: int | None) -> str:
    return f"{int(value or 0):,}".replace(",", ".")


def _date(value: datetime | None) -> str:
    return value.astimezone().strftime("%d/%m/%Y %H:%M") if value else "Sem registro"


def _execution_html(execution: dict[str, Any]) -> str:
    status = str(execution["status"]).upper()
    errors = execution.get("errors") or []
    error_rows = "".join(
        "<li>"
        f'<code>{escape(str(error.get("scope") or "coleta"))}</code>'
        f'<span>{escape(str(error.get("error") or "Erro não informado"))}</span>'
        "</li>"
        for error in errors
    )
    details = (
        '<div class="failure-block"><strong>Páginas, categorias ou lotes com falha</strong>'
        f'<ol class="failure-lines">{error_rows}</ol></div>'
        if error_rows
        else ""
    )
    count = execution.get("product_count")
    priced = execution.get("priced_product_count")
    counts = (
        f'<span>{_number(count)} itens</span><span>{_number(priced)} com preço</span>'
        if count is not None
        else '<span>Sem contagem: execução não persistida</span>'
    )
    return (
        '<article class="execution">'
        '<div class="execution-heading"><div>'
        f'<time>{_date(execution.get("occurred_at"))}</time>'
        f'<div class="execution-counts">{counts}</div></div>'
        f'<span class="status {escape(status)}">{STATUS_LABELS.get(status, escape(status))}</span>'
        f"</div>{details}</article>"
    )


def render_update_dashboard(sources: list[dict[str, Any]]) -> str:
    total_items = sum(int(source.get("latest_product_count") or 0) for source in sources)
    latest = max(
        (source["latest_collected_at"] for source in sources if source.get("latest_collected_at")),
        default=None,
    )
    sources_with_failure = sum(
        bool(source.get("executions") and source["executions"][0]["status"] in {"FAILED", "PARTIAL_SUCCESS"})
        for source in sources
    )
    source_cards = []
    for source in sources:
        executions = source.get("executions") or []
        current_status = executions[0]["status"] if executions else "SUCCESS"
        source_cards.append(
            '<section class="source-log">'
            '<header class="source-heading"><div>'
            f'<span class="source-name">{escape(source["name"])}</span>'
            f'<h2>{_number(source.get("latest_product_count"))} itens na última coleta</h2>'
            f'<p>{_number(source.get("latest_priced_product_count"))} com preço · '
            f'{_date(source.get("latest_collected_at"))}</p></div>'
            f'<span class="status {escape(current_status)}">'
            f'{STATUS_LABELS.get(current_status, escape(current_status))}</span></header>'
            '<div class="execution-list">'
            f'{"".join(_execution_html(execution) for execution in executions) or "<p class=\"empty\">Nenhuma execução registrada.</p>"}'
            "</div></section>"
        )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Log de atualizações</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<link rel="stylesheet" href="/static/updates.css?v=20260829-1"></head>
<body><header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<a class="back-link" href="/catalog">← Voltar aos produtos</a></div></header>
<main class="shell updates-main"><section class="updates-hero"><div><span class="eyebrow">Observabilidade</span>
<h1>Log de atualizações</h1><p>Acompanhe cada fonte, o volume processado e todas as páginas que apresentaram falha.</p></div>
<a class="refresh-page" href="/catalog/updates">Atualizar agora</a></section>
<section class="update-metrics">
<article><span>Fontes monitoradas</span><strong>{len(sources)}</strong></article>
<article><span>Itens nas últimas coletas</span><strong>{_number(total_items)}</strong></article>
<article><span>Fontes com alerta recente</span><strong>{sources_with_failure}</strong></article>
<article><span>Última atividade</span><strong class="metric-date">{_date(latest)}</strong></article>
</section><div class="source-logs">{"".join(source_cards)}</div></main></body></html>"""
