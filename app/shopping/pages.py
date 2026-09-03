"""Server-rendered shopping list screens (index + builder)."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from app.enrichment.dashboard import RETAILER_LABELS

_CSS = """
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}
.review-search{flex:1 1 260px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px;background:#fff}
.review-search input{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;background:transparent}
.pick{display:grid;gap:6px;max-height:320px;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:8px;margin-bottom:14px}
.pick-row{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:8px;flex-wrap:wrap}
.pick-row:hover{background:#f2f7f4}
.pick-row .cat{flex:1;font-weight:700;font-size:14px}
.chiplink{border:1px solid var(--line);background:#f6f9f7;color:var(--green);border-radius:99px;padding:4px 10px;font-size:12px;cursor:pointer}
.chiplink:hover{background:var(--green);color:#fff}
.sli-table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden}
.sli-table th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:10px 12px;background:#fafcfb;border-bottom:1px solid var(--line)}
.sli-table td{padding:9px 12px;border-bottom:1px solid #eef2f0;font-size:13px;vertical-align:top}
.sli-item h4{margin:0;font-size:14.5px}
.sli-item .muted{font-weight:400;color:var(--muted);font-size:12px}
.detail{display:inline-block;font-size:11.5px;color:#51615a;background:#f1f6f3;border-radius:8px;padding:4px 8px;margin-top:5px}
input.qty{width:64px;padding:6px 8px;border:1px solid var(--line);border-radius:8px}
select.src{padding:6px 8px;border:1px solid var(--line);border-radius:8px;min-width:160px;background:#fff}
input.note{width:120px;padding:5px 8px;border:1px solid var(--line);border-radius:8px}
td.price{white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
td.price b{font-size:15px;color:var(--green)}
.del{color:var(--red);background:none;border:0;font-size:18px;cursor:pointer}
.totalbar{position:sticky;bottom:10px;background:var(--green);color:#fff;border-radius:14px;padding:13px 18px;display:flex;gap:18px;align-items:center;margin-top:14px;box-shadow:var(--shadow);flex-wrap:wrap}
.totalbar b{font-size:22px}
.totalbar .muted{color:#cfe8dd;font-weight:600}
.empty{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted)}
.listcard{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.listcard a{color:var(--green);font-weight:700;text-decoration:none}
.hint{font-size:12px;color:var(--muted)}
@media(max-width:720px){.sli-table,.sli-table tbody,.sli-table tr,.sli-table td{display:block}.sli-table thead{display:none}.sli-table td{border-bottom:1px solid #eef2f0}}
"""


def _brl(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _page(title: str, inner: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>{escape(title)}</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>{_CSS}</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Lista de compras</span></div></header>
<main class="shell">{inner}</main></body></html>"""


def _tabs(active: str) -> str:
    items = [
        ("cuts", "/catalog/cuts", "Comparativo R$/kg"),
        ("review", "/catalog/butcher-review", "Revisão"),
        ("categories", "/catalog/categories", "Categorias"),
        ("shopping", "/shopping-lists", "Lista"),
    ]
    links = "".join(
        f'<a href="{href}"{" class=\"active\"" if key == active else ""}>{label}</a>'
        for key, href, label in items
    )
    return f'<nav class="view-tabs" aria-label="Visões">{links}</nav>'


def render_index(lists: list[dict[str, Any]]) -> str:
    cards = []
    for row in lists:
        cards.append(
            "<div class='listcard'><div>"
            f"<a href='/shopping-lists/{row['id']}'>{escape(row['name'])}</a>"
            f"<div class='hint'>{row['item_count']} item(ns)</div></div>"
            f"<form method='post' action='/shopping-lists/{row['id']}/delete' "
            "onsubmit=\"return confirm('Apagar esta lista?')\">"
            "<button class='del'>×</button></form></div>"
        )
    body = "".join(cards) or '<div class="empty">Nenhuma lista ainda — crie uma abaixo.</div>'
    inner = (
        _tabs("shopping")
        + "<section class='hero'><div><span class='eyebrow'>Lista de compras</span>"
        "<h1>Minhas listas</h1>"
        "<p>Cada item começa na fonte mais barata; você pode trocar a fonte item a item.</p>"
        "</div></section>"
        + "<div class='tools'><form method='post' action='/shopping-lists' "
        "style='display:flex;gap:8px;flex:1;flex-wrap:wrap'>"
        "<input style='flex:1;min-width:220px;padding:10px 12px;border:1px solid var(--line);"
        "border-radius:10px' name='name' required placeholder='Nome da nova lista…'>"
        "<button class='page-button' style='background:var(--green);color:#fff'>Criar lista</button>"
        "</form></div>" + body
    )
    return _page("Lista de compras", inner)


def render_builder(
    name: str,
    list_id: int,
    rows: list[dict[str, Any]],
    list_items: list[dict[str, Any]],
) -> str:
    # compact comparable rows keyed "category|form" with per-source price/store/sample
    row_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        sources = []
        for slug, info in (row.get("sources") or {}).items():
            if info.get("price_kg") is None:
                continue
            sources.append(
                {
                    "slug": slug,
                    "price": float(info["price_kg"]),
                    "store": info.get("store"),
                    "sample": info.get("sample"),
                }
            )
        if not sources:
            continue
        sources.sort(key=lambda s: s["price"])
        key = f"{row['category']}|{row['form']}"
        row_map[key] = {
            "label": row.get("label") or row["form"],
            "category": row["category"],
            "form": row["form"],
            "sources": sources,
        }

    item_rows = [_item_row(it, row_map) for it in list_items]
    payload_rows = json.dumps(row_map, ensure_ascii=False)
    inner = (
        _tabs("shopping")
        + "<section class='hero'><div><span class='eyebrow'>Lista de compras</span>"
        f"<h1>{escape(name)}</h1>"
        "<p>Busque e adicione itens classificados. A fonte padrão é a mais barata; "
        "troque na coluna <b>Fonte</b> para comprar em outra rede.</p></div>"
        "<a class='page-button' href='/shopping-lists'>← listas</a></section>"
        + "<div class='tools'><div class='review-search'><input id='search' type='search' "
        "placeholder='Buscar item p/ adicionar (ex.: Picanha, Bacon, Carne Moída)…'></div>"
        "<span class='hint' id='hint'></span></div>"
        + "<div class='pick' id='pick' style='display:none'></div>"
        + "<table class='sli-table'><thead><tr><th>Item (detalhe do produto)</th>"
        "<th>Fonte (onde comprar)</th><th>Qtd (kg)</th><th>Valor</th><th>Obs</th><th></th>"
        "</tr></thead><tbody id='items'>" + "".join(item_rows) + "</tbody></table>"
        + '<div class="empty" id="empty" style="display:none">Nenhum item ainda — busque acima.</div>'
        + "<div class='totalbar'><span>Sua lista (fontes escolhidas)</span>"
        "<b id='total'>R$ 0,00</b><span class='muted'>menor preço possível: "
        "<b id='totalmin'>R$ 0,00</b></span></div>"
    )
    return _page(f"Lista: {name}", inner) + _script(payload_rows, list_items, list_id)


def _item_row(it: dict[str, Any], row_map: dict[str, Any]) -> str:
    key = f"{it['category']}|{it['form']}"
    info = row_map.get(key)
    sources = (info or {}).get("sources") or []
    chosen = it["retailer"] or (sources[0]["slug"] if sources else "")
    select_opts = "".join(
        f"<option value=\"{s['slug']}\"{' selected' if s['slug'] == chosen else ''}>"
        f"{escape(RETAILER_LABELS.get(s['slug'], s['slug']))} — {_brl(s['price'])}</option>"
        for s in sources
    )
    if sources:
        base = next((s for s in sources if s["slug"] == chosen), sources[0])
        detail_parts = [RETAILER_LABELS.get(base["slug"], base["slug"])]
        if base.get("store"):
            detail_parts.append(str(base["store"]))
        if base.get("sample"):
            detail_parts.append(str(base["sample"]))
        detail = escape(" · ".join(detail_parts))
    else:
        detail = "—"
    note = escape(it.get("note") or "")
    return (
        "<tr class='sli' data-id='" + str(it["id"]) + "'>"
        f"<td><input type='hidden' class='cat' value=\"{escape(it['category'])}\">"
        f"<input type='hidden' class='formv' value=\"{escape(it['form'])}\">"
        f"<div class='sli-item'><h4>{escape(it['category'])}"
        f"<span class='muted'> · {escape(it['form'])}</span></h4></div>"
        f"<div class='detail'>{detail}</div></td>"
        f"<td><select class='src'>{select_opts or '<option value=\"\">—</option>'}</select></td>"
        f"<td><input class='qty' type='number' min='0.1' step='0.1' value=\"{it['qty']:g}\"></td>"
        f"<td class='price'>—</td>"
        f"<td><input class='note' type='text' placeholder='obs.' value=\"{note}\"></td>"
        "<td><button class='del rm' type='button'>×</button></td></tr>"
    )


def _script(rows_json: str, list_items: list[dict[str, Any]], list_id: int) -> str:
    template = """<script>
(function(){
  const LIST_ID = @@LIST_ID@@;
  const ROWS = @@ROWS@@;
  const LABEL = {'arena-atacado':'Arena','goodbom':'GoodBom','atacadao':'Atacadão','savegnago':'Savegnago','davitta':'Davitta','assai':'Assaí','tenda':'Tenda','sao-vicente':'São Vicente','max-atacadista':'Max'};
  const fmt = v => 'R$ ' + Number(v).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2});
  const key = (c,f) => c + '|' + f;
  const label = s => LABEL[s] || s;
  const cats = {};
  for (const k in ROWS) { const [c,f] = k.split('|'); (cats[c] = cats[c] || []).push(f); }
  const catList = Object.keys(cats).sort();
  const search = document.getElementById('search');
  const pick = document.getElementById('pick');
  const hint = document.getElementById('hint');
  const empty = document.getElementById('empty');

  function renderPick() {
    const t = (search.value || '').trim().toLowerCase();
    const show = catList.filter(c => {
      if (!t) return true;
      if (c.toLowerCase().includes(t)) return true;
      for (const f of cats[c]) {
        if (ROWS[key(c,f)].sources.some(s => ((s.sample||'') + ' ' + (s.store||'')).toLowerCase().includes(t))) return true;
      }
      return false;
    });
    pick.innerHTML = '';
    for (const c of show.slice(0, 40)) {
      const row = document.createElement('div'); row.className = 'pick-row';
      const cat = document.createElement('span'); cat.className = 'cat'; cat.textContent = c;
      const forms = document.createElement('span'); forms.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap';
      for (const f of cats[c]) {
        const src = ROWS[key(c,f)].sources[0];
        const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'chiplink';
        chip.textContent = f + ' — ' + label(src.slug) + ' ' + fmt(src.price);
        chip.title = 'Adicionar';
        chip.onclick = async () => {
          const r = await fetch('/shopping-lists/' + LIST_ID + '/items', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({category:c, form:f, retailer:src.slug, qty:1})
          });
          if (r.ok) location.reload(); else alert('Falha ao adicionar');
        };
        forms.appendChild(chip);
      }
      row.appendChild(cat); row.appendChild(forms); pick.appendChild(row);
    }
    pick.style.display = show.length ? 'block' : 'none';
    hint.textContent = show.length ? (show.length + (show.length > 40 ? '+' : '') + ' categorias — clique numa forma para adicionar') : '';
  }
  search.addEventListener('input', renderPick);

  const rows = [...document.querySelectorAll('#items tr.sli')];
  function compute() {
    let total = 0, totalmin = 0;
    for (const tr of rows) {
      const c = tr.querySelector('.cat').value, f = tr.querySelector('.formv').value;
      const info = ROWS[key(c,f)];
      if (!info) continue;
      const sel = tr.querySelector('select.src');
      const src = info.sources.find(s => s.slug === sel.value) || info.sources[0];
      const qty = parseFloat(tr.querySelector('input.qty').value) || 1;
      total += (src ? src.price : 0) * qty;
      totalmin += (info.sources[0] ? info.sources[0].price : 0) * qty;
      const det = tr.querySelector('.detail');
      if (det) {
        const parts = [src ? label(src.slug) : '—'];
        if (src && src.store) parts.push(src.store);
        if (src && src.sample) parts.push(src.sample);
        det.textContent = parts.join(' · ');
      }
      tr.querySelector('.price').innerHTML = src ? '<b>' + fmt(src.price * qty) + '</b>' : '—';
    }
    document.getElementById('total').textContent = fmt(total);
    document.getElementById('totalmin').textContent = fmt(totalmin);
    if (empty) empty.style.display = rows.length ? 'none' : 'block';
  }
  async function persist(id, payload) {
    try {
      await fetch('/shopping-lists/items/' + id, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
    } catch (e) {}
  }
  for (const tr of rows) {
    const id = tr.dataset.id;
    tr.querySelector('select.src').addEventListener('change', function(){ persist(id, {retailer: this.value}); compute(); });
    tr.querySelector('input.qty').addEventListener('input', function(){ persist(id, {qty: this.value}); compute(); });
    tr.querySelector('input.note').addEventListener('change', function(){ persist(id, {note: this.value}); });
    tr.querySelector('.rm').addEventListener('click', async function(){
      if (!confirm('Remover item?')) return;
      await fetch('/shopping-lists/items/' + id + '/delete', {method:'POST'});
      location.reload();
    });
  }
  compute();
  renderPick();
})();
</script>"""
    return (
        template.replace("@@LIST_ID@@", str(list_id)).replace("@@ROWS@@", rows_json)
    )
