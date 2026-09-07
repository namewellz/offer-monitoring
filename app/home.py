"""Initial dashboard ("hub") linking to every screen of the app.

Serves as the friendly landing page at ``/`` so each tool is one click away
(no need to type URLs). Cards are grouped by area and show small live metrics.
"""

from __future__ import annotations

from html import escape
from typing import Any

from sqlalchemy import func, select

from app.catalog.v2.read import latest_runs
from app.core.timezone import to_local
from app.db.models_v2 import ShoppingList

_GREEN = "#145c42"
_MUTED = "#64748b"

SECTIONS: list[dict[str, Any]] = [
    {
        "title": "Compras",
        "subtitle": "Monte e compare sua lista nos supermercados",
        "cards": [
            {
                "icon": "🛒",
                "title": "Lista de compras",
                "text": "Crie listas, busque pelo produto canônico e escolha onde comprar mais barato.",
                "href": "/shopping-lists",
                "primary": True,
            },
        ],
    },
    {
        "title": "Preços & Catálogo",
        "subtitle": "Consulte e acompanhe os preços dos supermercados",
        "cards": [
            {
                "icon": "📊",
                "title": "Catálogo de preços",
                "text": "Todos os produtos monitorados com o preço por loja.",
                "href": "/catalog",
            },
            {
                "icon": "🏷️",
                "title": "Em oferta",
                "text": "Somente os itens com desconto na coleta atual.",
                "href": "/catalog?view=offers",
            },
            {
                "icon": "📈",
                "title": "Variações de preço",
                "text": "Aumentos e reduções entre as últimas coletas.",
                "href": "/catalog?view=changes",
            },
            {
                "icon": "🔄",
                "title": "Atualizações (log)",
                "text": "Histórico e status das coletas automáticas e manuais.",
                "href": "/catalog/updates",
            },
            {
                "icon": "🗞️",
                "title": "Ofertas de encarte",
                "text": "Ofertas extraídas dos encartes (flyers).",
                "href": "/ofertas",
            },
        ],
    },
    {
        "title": "Onde comprar",
        "subtitle": "Compare o mesmo produto entre as lojas (identidade canônica)",
        "cards": [
            {
                "icon": "🍎",
                "title": "Hortifrúti",
                "text": "Frutas, verduras e legumes por identidade (ex.: Maçã Fuji).",
                "href": "/catalog/produce-prices",
            },
            {
                "icon": "🥩",
                "title": "Açougue (cortes)",
                "text": "Comparativo de cortes por quilo entre as lojas.",
                "href": "/catalog/cuts",
            },
            {
                "icon": "🏪",
                "title": "Por departamento",
                "text": "Preço por departamento (bebidas, mercearia, higiene...).",
                "href": "/catalog/dept-prices",
            },
        ],
    },
    {
        "title": "Revisão & Categorias",
        "subtitle": "Ferramentas de conferência e organização do catálogo",
        "cards": [
            {
                "icon": "🗂️",
                "title": "Categorias",
                "text": "Navegue pelas categorias e produtos classificados.",
                "href": "/catalog/categories",
            },
            {
                "icon": "🔬",
                "title": "Revisão do Açougue",
                "text": "Confira os cortes classificados pela IA.",
                "href": "/catalog/butcher-review",
            },
            {
                "icon": "🧭",
                "title": "Revisão de departamento",
                "text": "Revise a classificação por departamento.",
                "href": "/catalog/department-review",
            },
            {
                "icon": "📝",
                "title": "Marcações (encartes)",
                "text": "Revise as marcações extraídas dos encartes.",
                "href": "/annotation",
            },
        ],
    },
]

_CSS = f"""
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
background:#f4f7f5;color:#1c2733;line-height:1.5}}
a{{text-decoration:none;color:inherit}}
.topbar{{background:#0f3d2e;color:#fff}}
.topbar .inner{{max-width:1160px;margin:0 auto;padding:14px 22px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}}
.brand{{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.2px}}
.brand .mark{{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#2fbf71,#16a35c);
display:inline-flex;align-items:center;justify-content:center;font-weight:900;color:#fff}}
.brand small{{display:block;font-weight:500;color:#b9e6cf;font-size:11px;letter-spacing:.4px;text-transform:uppercase}}
.nav{{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}}
.nav a{{color:#eafff4;font-size:13px;padding:7px 12px;border-radius:99px}}
.nav a:hover{{background:#ffffff1a}}
.hero{{background:linear-gradient(135deg,#0f3d2e 0%,#145c42 55%,#1e7a55 100%);color:#fff;
padding:44px 22px 38px}}
.hero .inner{{max-width:1160px;margin:0 auto}}
.hero h1{{margin:4px 0 8px;font-size:30px;letter-spacing:.3px}}
.hero p{{margin:0;color:#cfe9db;max-width:760px;font-size:15px}}
.metrics{{display:flex;gap:14px;margin-top:22px;flex-wrap:wrap}}
.metric{{background:#ffffff1f;border:1px solid #ffffff2e;border-radius:14px;padding:10px 18px}}
.metric b{{display:block;font-size:22px}}
.metric span{{font-size:12px;color:#cfe9db}}
main{{max-width:1160px;margin:0 auto;padding:26px 22px 60px}}
section{{margin-bottom:34px}}
.sec-head h2{{margin:0 0 2px;font-size:19px}}
.sec-head p{{margin:0 0 14px;color:{_MUTED};font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}}
.card{{background:#fff;border:1px solid #e3ece7;border-radius:16px;padding:18px;display:flex;flex-direction:column;
gap:8px;box-shadow:0 1px 2px #0f3d2e08;transition:transform .08s ease, box-shadow .12s ease;position:relative}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 22px #0f3d2e1a;border-color:#bfe0d0}}
.card .ico{{font-size:26px}}
.card h3{{margin:0;font-size:16px;color:#12432f}}
.card p{{margin:0;font-size:13px;color:{_MUTED};flex:1}}
.card.primary{{border:2px solid {_GREEN};background:linear-gradient(180deg,#f0faf4,#ffffff)}}
.card .go{{position:absolute;right:14px;top:14px;color:#9db8a9;font-weight:800}}
.card:hover .go{{color:{_GREEN}}}
footer{{max-width:1160px;margin:0 auto;padding:0 22px 30px;color:#7b8b83;font-size:12px}}
"""


def _metric(label: str, value: str) -> str:
    return f'<div class="metric"><b>{escape(value)}</b><span>{escape(label)}</span></div>'


def render_home(db: Any) -> str:
    runs = latest_runs(db)
    supermarkets = len(runs)
    products = sum(int(run.get("product_count") or 0) for run in runs)
    last_run = max(
        (run.get("collected_at") for run in runs if run.get("collected_at")), default=None
    )
    lists_count = int(db.scalar(select(func.count()).select_from(ShoppingList)) or 0)

    sections = "".join(
        "<section><div class='sec-head'><h2>"
        f"{escape(section['title'])}</h2><p>{escape(section['subtitle'])}</p></div>"
        "<div class='grid'>"
        + "".join(
            "<a class='card"
            + (" primary" if card.get("primary") else "")
            + f"' href='{escape(card['href'])}'>"
            + f"<span class='go'>→</span><span class='ico'>{card['icon']}</span>"
            f"<h3>{escape(card['title'])}</h3><p>{escape(card['text'])}</p></a>"
            for card in section["cards"]
        )
        + "</div></section>"
        for section in SECTIONS
    )

    last_label = to_local(last_run).strftime("%d/%m às %H:%M") if last_run else "—"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f3d2e"><title>Monitor de Preços</title>
<style>{_CSS}</style></head><body>
<header class="topbar"><div class="inner">
<a class="brand" href="/"><span class="mark">OM</span><span>Offer Monitor<small>Preços & Compras</small></span></a>
<nav class="nav">
<a href="/catalog">Catálogo</a><a href="/shopping-lists">Lista de compras</a>
<a href="/catalog/produce-prices">Hortifrúti</a><a href="/catalog/cuts">Açougue</a>
<a href="/catalog/updates">Atualizações</a></nav></div></header>
<section class="hero"><div class="inner">
<h1>Monitor de Preços</h1>
<p>Consulte preços, compare o mesmo produto entre supermercados e monte sua
lista de compras. Tudo em um só lugar — escolha abaixo por onde começar.</p>
<div class="metrics">
{_metric("supermercados ativos", f"{supermarkets}")}
{_metric("produtos monitorados", f"{products:,}".replace(",", "."))}
{_metric("listas de compras", f"{lists_count}")}
{_metric("última coleta", last_label)}
</div></div></section>
<main>{sections}</main>
<footer>Offer Monitor · acompanhamento de preços e lista de compras ·
<a href="/catalog/updates">log de atualizações</a></footer>
</body></html>"""
