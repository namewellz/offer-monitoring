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


def render_butcher_dashboard(result: dict[str, Any]) -> str:
    groups = result["groups"]
    headers = "".join(
        f"<th>{escape(RETAILER_LABELS.get(slug, slug))}</th>" for slug in RETAILER_ORDER
    )
    rows: list[str] = []
    for group in groups:
        sources = group["sources"]
        prices = [sources.get(slug, {}).get("price_kg") for slug in RETAILER_ORDER]
        present = [p for p in prices if p is not None]
        cheapest = min(present) if present else None
        cells = []
        for slug, price in zip(RETAILER_ORDER, prices, strict=True):
            if price is None:
                cells.append("<td class=\"na\">—</td>")
                continue
            cls = "best" if price == cheapest else ""
            sample = escape(sources[slug].get("sample") or "")
            cells.append(
                f'<td class="{cls}" title="{sample}">{_brl(price)}</td>'
            )
        rows.append(
            '<tr>'
            f'<td class="cut"><strong>{escape(group["label"])}</strong>'
            f'<span class="muted">{escape(group.get("conservation") or "")}</span></td>'
            + "".join(cells)
            + "</tr>"
        )
    empty = '<tr><td colspan="10">Nenhum corte comparável encontrado.</td></tr>'
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Açougue — comparação por kg</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.cut .muted{{display:block;font-size:12px;color:#607080;font-weight:400}}
td.na{{color:#b0b8c0}}td.best{{background:#e3f6e9;font-weight:700;color:#067647}}
table{{min-width:900px}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Açougue</span></div></header>
<main class="shell">
<section class="hero"><div><span class="eyebrow">Comparação determinística</span>
<h1>Açougue — preço por kg</h1>
<p>{result['total_groups']} cortes agrupados a partir de {result['total_items']} itens. Preços por kg; o menor de cada linha está destacado. Passe o mouse para ver o nome original.</p></div></section>
<div class="table"><table><thead><tr><th>Corte</th>{headers}</tr></thead>
<tbody>{''.join(rows) or empty}</tbody></table></div>
</main></body></html>"""
