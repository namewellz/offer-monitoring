"""HTML for the per-department classification review screen."""

from __future__ import annotations

from html import escape
from typing import Any


def _br(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def dept_selector(department: str) -> str:
    """Dropdown de departamento que navega na tela de revisão (/catalog/butcher-review)."""
    from app.catalog.taxonomy import CANONICAL_DEPARTMENTS

    options = "".join(
        f'<option value="{escape(d)}"{" selected" if d == department else ""}>'
        f"{escape(d)}</option>"
        for d in CANONICAL_DEPARTMENTS
    )
    return (
        "<span class='deptsel'><label>Departamento</label>"
        "<select onchange=\"location.href='/catalog/butcher-review?department='"
        "+encodeURIComponent(this.value)\" title='Trocar departamento'>"
        f"{options}</select></span>"
    )


def render_department_review_page(data: dict[str, Any]) -> str:
    department = data["department"]
    groups = data["groups"]
    rejected = data["rejected_rows"]
    card = (
        "<section class='hero'><div><span class='eyebrow'>Revisão de classificação</span>"
        f"<h1>{escape(department)}</h1>"
        "<p>Produtos aceitos agrupados por categoria canônica, com amostras "
        "para conferir falsos positivos e consistência. Os rejeitados ficam no "
        "final (fora do departamento).</p></div>"
        f"<a class='page-button' href='/catalog/categories?department={escape(department)}'>"
        "Categorias</a></section>"
    )
    chips = (
        "<div class='tools'>"
        + dept_selector(department)
        + f"<span class='chip-stat'><b>{_br(data['accepted_products'])}</b> aceitos</span>"
        + f"<span class='chip-stat'><b>{_br(data['rejected_products'])}</b> fora do dept</span>"
        + f"<span class='chip-stat'><b>{_br(data['distinct_canonicals'])}</b> categorias</span>"
        "</div>"
    )
    rows: list[str] = []
    for group in groups:
        samples = "".join(
            f"<li><span class='r'>{escape(item['retailer'])}</span> — {escape(item['name'])}</li>"
            for item in group["samples"]
        )
        variants = ", ".join(
            f"{escape(label)}{(' ×' + _br(count)) if count > 1 else ''}"
            for label, count in list(group["labels"].items())[:3]
        )
        rows.append(
            "<tr>"
            f"<td class='canon'>{escape(group['canonical'])}</td>"
            f"<td class='n'>{_br(group['count'])}</td>"
            f"<td class='vars'>{escape(variants) or '—'}</td>"
            f"<td><ul class='samples'>{samples}</ul></td>"
            "</tr>"
        )
    table = (
        "<div class='table-wrap'><table class='dtable'>"
        "<thead><tr><th>Categoria canônica</th><th>Produtos</th>"
        "<th>Como a LLM escreveu</th><th>Amostras</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    reject_list = "".join(
        f"<li><span class='r'>{escape(item['retailer'])}</span> — {escape(item['name'])}"
        + (f" <em>({escape(item['reason'])})</em>" if item["reason"] else "")
        + "</li>"
        for item in rejected
    )
    rejected_html = (
        f"<details class='rej'><summary>Fora do departamento — amostra "
        f"({_br(data['rejected_products'])} no total, mostrando "
        f"{len(rejected)})</summary><ul class='samples'>{reject_list or '<li>—</li>'}</ul>"
        "</details>"
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>{escape(department)} — revisão</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.tools{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}}
.deptsel{{display:flex;gap:8px;align-items:center;margin-right:6px}}
.deptsel label{{font-size:12px;color:var(--muted);font-weight:700;white-space:nowrap}}
.deptsel select{{padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px;background:#fff;color:var(--ink)}}
.chip-stat{{font-size:13px;color:var(--muted)}}.chip-stat b{{font-size:17px;color:var(--green);display:block}}
.dtable{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden}}
.dtable th{{text-align:left;font-size:11px;text-transform:uppercase;color:var(--muted);padding:10px 12px;background:#fafcfb;border-bottom:1px solid var(--line)}}
.dtable td{{padding:9px 12px;border-bottom:1px solid #eef2f0;font-size:13px;vertical-align:top}}
td.canon{{font-weight:700}}
td.n{{color:var(--muted);text-align:center}}
td.vars{{color:#51615a;font-size:11.5px;max-width:220px}}
ul.samples{{margin:0;padding:0;list-style:none}}
ul.samples li{{font-size:12px;color:#3a4a42;padding:1px 0}}
ul.samples .r{{display:inline-block;font-size:10.5px;font-weight:700;color:var(--green);background:#eef6f1;border-radius:6px;padding:0 6px;margin-right:4px}}
.rej{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-top:14px}}
.rej summary{{cursor:pointer;font-weight:700;color:#51615a}}
.rej em{{color:var(--muted)}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> {escape(department)}</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões">
<a href="/catalog/cuts">Comparativo R$/kg</a>
<a class="active" href="/catalog/department-review?department={escape(department)}">Revisão por dept</a>
<a href="/catalog/categories?department={escape(department)}">Categorias</a>
<a href="/shopping-lists">Lista</a>
</nav>
{card}{chips}{table}{rejected_html}
</main></body></html>"""
