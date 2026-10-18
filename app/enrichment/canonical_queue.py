"""Shared HTML for the B1–B4 and R queues on the review screens."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

from app.canonical.review_queue import GROUPS, GROUP_LABELS


def _br(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def render_canonical_queue(queue: dict | None) -> str:
    if not queue:
        return ""
    department = queue["department"]
    base = queue["base"]
    chosen = queue.get("group")
    chips = []
    for code in GROUPS:
        count = int(queue["counts"].get(code) or 0)
        href = f"{base}?department={quote(department)}&fila={code}"
        mark = " on" if code == chosen else ""
        chips.append(
            f'<a class="qchip{mark}" href="{escape(href)}">{code} · {_br(count)}</a>'
        )
    body = ""
    if chosen:
        rows = []
        for item in queue["rows"]:
            pack = item["pack"]
            rows.append(
                "<tr>"
                f"<td>{escape(item['name'])}</td>"
                f"<td>{escape(item['brand']) or '—'}</td>"
                f"<td>{escape(item['size']) or '—'}</td>"
                f"<td>{_br(pack) if pack else '—'}</td>"
                f"<td>{escape(item['retailer'])}</td>"
                "</tr>"
            )
        shown = len(queue["rows"])
        total = int(queue["total"])
        note = f"Mostrando {shown} de {_br(total)}." if total else "Nenhum item neste grupo."
        body = (
            f"<p class='qnote'><b>{escape(chosen)}</b> — {escape(queue.get('label') or '')}. {note}</p>"
            "<div class='table-wrap'><table class='qtable'><thead><tr>"
            "<th>Produto</th><th>Marca</th><th>Tamanho</th><th>Pack</th><th>Rede</th>"
            f"</tr></thead><tbody>{''.join(rows) or '<tr><td colspan=5>Nenhum item.</td></tr>'}"
            "</tbody></table></div>"
        )
    return f"""<section class="canon-queue">
<style>
.canon-queue{{margin:18px 0;background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px}}
.canon-queue h2{{margin:0 0 4px;font-size:16px}}
.canon-queue .qlead{{margin:0 0 10px;color:var(--muted);font-size:13px}}
.qchips{{display:flex;gap:8px;flex-wrap:wrap}}
.qchip{{padding:7px 10px;border-radius:99px;border:1px solid var(--line);font-size:12px;font-weight:700;color:#145c42;text-decoration:none}}
.qchip.on{{background:#145c42;color:#fff;border-color:#145c42}}
.qnote{{font-size:13px;color:#51615a}}
.qtable{{width:100%;border-collapse:collapse}}
.qtable th{{text-align:left;font-size:11px;text-transform:uppercase;color:var(--muted);padding:8px}}
.qtable td{{padding:8px;border-top:1px solid #eef2f0;font-size:13px;vertical-align:top}}
</style>
<h2>Fila canônica</h2>
<p class="qlead">Itens deste departamento que ainda não entram na cobertura automática.
{escape(GROUP_LABELS['B1'])} (B1), kit (B2), sem medida (B3), sem marca (B4) e GTIN com 1 un (R).</p>
<div class="qchips">{''.join(chips)}</div>
{body}
</section>"""
