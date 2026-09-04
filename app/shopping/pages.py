"""Server-rendered shopping list screens (index + builder).

Layout do builder (prioridade = os itens adicionados ficam na tela):
  1) abas + título
  2) tabela dos itens da lista (departamento · produto · unidade · detalhe,
     origem, quantidade SEMPRE visível com default 1, valor, obs)
  3) totalizador fixo
  4) seção "Adicionar itens" (busca abre resultados só ao digitar)
"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from app.enrichment.dashboard import RETAILER_LABELS

_CSS = """
.addsec{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;margin-top:4px}
.addsec h2{margin:0 0 10px;font-size:16px;color:var(--green)}
.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;border:1px solid var(--line);border-radius:12px;padding:8px 10px;background:#fafcfb}
.review-search{flex:1 1 260px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px;background:#fff}
.review-search input{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;background:transparent}
.pick{display:grid;gap:6px;max-height:360px;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:12px;padding:8px;margin-top:10px}
.pick-row{display:flex;align-items:flex-start;gap:10px;padding:6px 8px;border-radius:8px;flex-wrap:wrap}
.pick-row:hover{background:#f2f7f4}
.pick-row .cat{flex:1;font-weight:700;font-size:14px;min-width:140px}
.pick-row .cat .dept{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;margin-top:3px}
.chiplink{border:1px solid var(--line);background:#f6f9f7;color:var(--green);border-radius:99px;padding:4px 10px;font-size:12px;cursor:pointer}
.chiplink:hover{background:var(--green);color:#fff}
.sli-table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden}
.sli-table th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:10px 12px;background:#fafcfb;border-bottom:1px solid var(--line)}
.sli-table td{padding:9px 12px;border-bottom:1px solid #eef2f0;font-size:13px;vertical-align:top}
.sli-table td .dept{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--green);background:#e7f3ee;border-radius:99px;padding:2px 8px}
.sli-item h4{margin:4px 0 4px;font-size:15px}
.uni{display:inline-block;font-size:11.5px;color:#51615a;background:#f1f6f3;border-radius:8px;padding:2px 8px;font-weight:600}
.detail{display:block;font-size:11.5px;color:#5a6b63;margin-top:5px;line-height:1.35;max-width:420px}
input.qty{width:58px;padding:6px 8px;border:1px solid var(--line);border-radius:8px}
.qtywrap{display:flex;align-items:center;gap:6px;white-space:nowrap}
.qtywrap .uk{color:var(--muted);font-size:12px;font-weight:700}
select.src{padding:6px 8px;border:1px solid var(--line);border-radius:8px;min-width:170px;background:#fff}
input.note{width:96px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;font-size:12px}
td.price{white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
td.price b{font-size:15px;color:var(--green)}
td.price .pkg{display:block;font-size:10.5px;color:var(--muted);font-weight:600;text-align:right}
.del{color:var(--red);background:none;border:0;font-size:18px;cursor:pointer}
.totalbar{position:sticky;bottom:10px;background:var(--green);color:#fff;border-radius:14px;padding:13px 18px;display:flex;gap:18px;align-items:center;margin:14px 0;box-shadow:var(--shadow);flex-wrap:wrap}
.totalbar b{font-size:22px}
.totalbar .muted{color:#cfe8dd;font-weight:600}
.empty{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:26px;text-align:center;color:var(--muted)}
.listcard{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.listcard a{color:var(--green);font-weight:700;text-decoration:none}
.hint{font-size:12px;color:var(--muted)}
@media(max-width:720px){.sli-table,.sli-table tbody,.sli-table tr,.sli-table td{display:block}.sli-table thead{display:none}.sli-table td{border-bottom:1px solid #eef2f0;padding:8px 12px}}
"""


def _brl(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


_UNIT_TITLE = {"kg": "kg", "L": "litro", "un": "unidade"}


def _unit_title(unit: str) -> str:
    return _UNIT_TITLE.get(unit, unit)


def _line_title(department: str, label: str, unit: str) -> str:
    """Rótulo da unidade exibido no item: Açougue mostra a forma de venda;
    demais departamentos mostram 'por kg/L/unidade'."""
    if department == "Açougue":
        return f"{label} · {unit}"
    return f"por {_unit_title(unit)}"


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
    # compact comparable rows keyed "department|category|form/unit" with sources
    row_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        department = row.get("department") or "Açougue"
        unit = row.get("unit") or "kg"
        sources = []
        for slug, info in (row.get("sources") or {}).items():
            price = info.get("price") if isinstance(info, dict) else None
            if price is None:
                continue
            sources.append(
                {
                    "slug": slug,
                    "price": float(price),
                    "store": info.get("store") if isinstance(info, dict) else None,
                    "sample": info.get("sample") if isinstance(info, dict) else None,
                }
            )
        if not sources:
            continue
        sources.sort(key=lambda s: s["price"])
        key = f"{department}|{row['category']}|{row['form']}"
        row_map[key] = {
            "department": department,
            "unit": unit,
            "label": row.get("label") or row["form"],
            "category": row["category"],
            "form": row["form"],
            "sources": sources,
        }

    item_rows = [_item_row(it, row_map) for it in list_items]
    payload_rows = json.dumps(row_map, ensure_ascii=False)
    has_items = bool(item_rows)
    table = (
        "<table class='sli-table' id='sltable'>"
        "<thead><tr><th>Item (departamento · produto · unidade)</th>"
        "<th>Origem (onde comprar)</th><th>Qtd</th><th>Valor</th>"
        "<th>Obs</th><th></th></tr></thead>"
        f"<tbody id='items'>{''.join(item_rows)}</tbody></table>"
    )
    empty = (
        "<div class='empty' id='empty' style='"
        + ("display:none" if has_items else "")
        + "'>Nenhum item ainda — use a busca abaixo para adicionar.<br>"
        "Cada item entra com quantidade <b>1</b> (a caixa fica na tela para você ajustar).</div>"
    )
    inner = (
        _tabs("shopping")
        + "<section class='hero'><div><span class='eyebrow'>Lista de compras</span>"
        f"<h1>{escape(name)}</h1>"
        "<p>Fonte padrão: <b>mais barata</b>. Troque a origem item a item e ajuste a "
        "quantidade direto na linha.</p></div>"
        "<a class='page-button' href='/shopping-lists'>← listas</a></section>"
        + table
        + empty
        + "<div class='totalbar'><span>Sua lista (fontes escolhidas)</span>"
        "<b id='total'>R$ 0,00</b><span class='muted'>menor preço possível: "
        "<b id='totalmin'>R$ 0,00</b></span></div>"
        + "<div class='addsec'><h2>Adicionar itens</h2>"
        "<div class='tools'><div class='review-search'><input id='search' type='search' "
        "placeholder='Buscar produto (ex.: Picanha, Bacon, Moída)…'></div>"
        "<span class='hint' id='hint'></span></div>"
        "<div class='pick' id='pick' style='display:none'></div></div>"
    )
    return _page(f"Lista: {name}", inner) + _script(payload_rows, list_items, list_id)


def _item_row(it: dict[str, Any], row_map: dict[str, Any]) -> str:
    department = it.get("department") or "Açougue"
    key = f"{department}|{it['category']}|{it['form']}"
    info = row_map.get(key)
    sources = (info or {}).get("sources") or []
    unit = (info or {}).get("unit") or "kg"
    label = (info or {}).get("label") or it["form"]
    dept = (info or {}).get("department") or department

    chosen = it["retailer"] if it["retailer"] else None
    detail = ""
    if not sources:
        select_opts = '<option value="">—</option>'
    else:
        if chosen not in [s["slug"] for s in sources]:
            chosen = sources[0]["slug"]
        select_opts = "".join(
            f"<option value=\"{s['slug']}\"{' selected' if s['slug'] == chosen else ''}>"
            f"{escape(RETAILER_LABELS.get(s['slug'], s['slug']))} — {_brl(s['price'])}"
            f"/{escape(unit)}"
            "</option>"
            for s in sources
        )
        base = next((s for s in sources if s["slug"] == chosen), sources[0])
        detail_parts = []
        if base.get("store"):
            detail_parts.append(str(base["store"]))
        if base.get("sample"):
            detail_parts.append(str(base["sample"]))
        detail = escape(" · ".join(detail_parts))
    note = escape(it.get("note") or "")
    qty = float(it.get("qty") or 1)
    qty_s = f"{qty:g}"
    uni_text = escape(_line_title(dept, label, unit))
    return (
        "<tr class='sli' data-id='" + str(it["id"]) + "'>"
        f"<td><input type='hidden' class='deptv' value=\"{escape(dept)}\">"
        f"<input type='hidden' class='cat' value=\"{escape(it['category'])}\">"
        f"<input type='hidden' class='formv' value=\"{escape(it['form'])}\">"
        f"<span class='dept'>{escape(dept)}</span>"
        f"<div class='sli-item'><h4>{escape(it['category'])}</h4>"
        f"<span class='uni'>{uni_text}</span>"
        f"<span class='detail'>{detail}</span></div></td>"
        f"<td><select class='src'>{select_opts}</select></td>"
        f"<td><div class='qtywrap'><input class='qty' type='number' min='0.1' step='0.1' "
        f"value=\"{qty_s}\"><span class='uk'>{escape(unit)}</span></div></td>"
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
  const key = (d,c,f) => d + '|' + c + '|' + f;
  const label = s => LABEL[s] || s;
  const UT = {'kg':'kg','L':'litro','un':'unidade'};
  const lineTitle = (d,lab,u) => d === 'Açougue' ? (lab + ' · ' + u) : ('por ' + (UT[u] || u));
  const cats = {};
  for (const k in ROWS) { const [d,c] = k.split('|'); (cats[d + '|' + c] = cats[d + '|' + c] || []).push(k); }
  const catList = Object.keys(cats).sort();
  const search = document.getElementById('search');
  const pick = document.getElementById('pick');
  const hint = document.getElementById('hint');
  const empty = document.getElementById('empty');
  const tableEl = document.getElementById('sltable');

  function renderPick() {
    const t = (search.value || '').trim().toLowerCase();
    if (!t) { pick.style.display = 'none'; pick.innerHTML = ''; hint.textContent = ''; return; }
    const show = catList.filter(gk => {
      const [d,c] = gk.split('|');
      if (c.toLowerCase().includes(t)) return true;
      if (d.toLowerCase().includes(t)) return true;
      for (const k of cats[gk]) {
        const info = ROWS[k];
        if (info.label.toLowerCase().includes(t)) return true;
        if (info.sources.some(s => ((s.sample||'') + ' ' + (s.store||'')).toLowerCase().includes(t))) return true;
      }
      return false;
    });
    pick.innerHTML = '';
    for (const gk of show.slice(0, 30)) {
      const [d,c] = gk.split('|');
      const first = ROWS[cats[gk][0]];
      const row = document.createElement('div'); row.className = 'pick-row';
      const cat = document.createElement('span'); cat.className = 'cat';
      const dept = document.createElement('span'); dept.className = 'dept';
      dept.textContent = first.department;
      cat.appendChild(document.createTextNode(c)); cat.appendChild(dept);
      const forms = document.createElement('span'); forms.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap';
      for (const k of cats[gk]) {
        const info = ROWS[k];
        const f = info.form;
        const src = info.sources[0];
        const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'chiplink';
        chip.textContent = lineTitle(d, info.label, info.unit) + ' · ' + label(src.slug) + ' ' + fmt(src.price) + '/' + info.unit;
        chip.title = 'Adicionar com quantidade 1 (ajuste na linha)';
        chip.onclick = async () => {
          chip.disabled = true;
          try {
            const r = await fetch('/shopping-lists/' + LIST_ID + '/items', {
              method: 'POST', headers: {'Content-Type':'application/json'},
              body: JSON.stringify({department:d, category:c, form:f, retailer:src.slug, qty:1})
            });
            if (r.ok) { addItem(await r.json()); } else { alert('Falha ao adicionar'); }
          } catch (e) { alert('Falha ao adicionar'); }
          chip.disabled = false;
        };
        forms.appendChild(chip);
      }
      row.appendChild(cat); row.appendChild(forms); pick.appendChild(row);
    }
    pick.style.display = show.length ? 'block' : 'none';
    hint.textContent = show.length
      ? (show.length + (show.length > 30 ? '+' : '') + ' produto(s) — clique numa forma para adicionar (qtd 1)')
      : 'Nada encontrado para "' + t + '"';
  }
  search.addEventListener('input', renderPick);

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  function makeRow(it) {
    const dept = it.department || 'Açougue';
    const info = ROWS[key(dept, it.category, it.form)];
    const sources = info ? info.sources : [];
    const unit = info ? info.unit : 'kg';
    const lab = info ? info.label : it.form;
    let chosen = it.retailer || (sources[0] ? sources[0].slug : '');
    if (sources.length && !sources.some(s => s.slug === chosen)) chosen = sources[0].slug;
    const opts = sources.map(s =>
      '<option value="' + esc(s.slug) + '"' + (s.slug === chosen ? ' selected' : '') + '>' +
      esc(label(s.slug)) + ' — ' + fmt(s.price) + '/' + unit + '</option>'
    ).join('') || '<option value="">—</option>';
    const base = sources.find(s => s.slug === chosen) || sources[0];
    const detParts = [];
    if (base && base.store) detParts.push(esc(base.store));
    if (base && base.sample) detParts.push(esc(base.sample));
    const qty = parseFloat(it.qty) || 1;
    const tr = document.createElement('tr'); tr.className = 'sli'; tr.dataset.id = it.id;
    tr.innerHTML =
      "<td><input type='hidden' class='deptv' value='" + esc(dept) + "'>" +
      "<input type='hidden' class='cat' value='" + esc(it.category) + "'>" +
      "<input type='hidden' class='formv' value='" + esc(it.form) + "'>" +
      "<span class='dept'>" + esc(dept) + "</span>" +
      "<div class='sli-item'><h4>" + esc(it.category) + "</h4>" +
      "<span class='uni'>" + esc(lineTitle(dept, lab, unit)) + "</span>" +
      "<span class='detail'>" + detParts.join(' · ') + "</span></div></td>" +
      "<td><select class='src'>" + opts + "</select></td>" +
      "<td><div class='qtywrap'><input class='qty' type='number' min='0.1' step='0.1' value='" + qty + "'><span class='uk'>" + esc(unit) + "</span></div></td>" +
      "<td class='price'>—</td>" +
      "<td><input class='note' type='text' placeholder='obs.' value=''></td>" +
      "<td><button class='del rm' type='button'>×</button></td>";
    return tr;
  }
  function bindRow(tr) {
    const id = tr.dataset.id;
    tr.querySelector('select.src').addEventListener('change', function(){ persist(id, {retailer: this.value}); compute(); });
    tr.querySelector('input.qty').addEventListener('input', function(){ persist(id, {qty: this.value}); compute(); });
    tr.querySelector('input.note').addEventListener('change', function(){ persist(id, {note: this.value}); });
    tr.querySelector('.rm').addEventListener('click', async function(){
      if (!confirm('Remover item?')) return;
      this.disabled = true;
      const r = await fetch('/shopping-lists/items/' + id + '/delete', {method:'POST'});
      if (r.ok) { tr.remove(); compute(); } else { this.disabled = false; alert('Falha ao remover'); }
    });
  }
  const tbody = document.getElementById('items');
  function addItem(it) {
    const d = it.department || 'Açougue';
    const k = key(d, it.category, it.form);
    let existing = null;
    for (const tr of tbody.querySelectorAll('tr.sli')) {
      if (key(tr.querySelector('.deptv').value, tr.querySelector('.cat').value, tr.querySelector('.formv').value) === k) { existing = tr; break; }
    }
    if (existing) {
      existing.querySelector('input.qty').value = parseFloat(it.qty) || 1;
      const sel = existing.querySelector('select.src');
      if (sel.querySelector('option[value="' + it.retailer + '"]')) sel.value = it.retailer;
    } else {
      const tr = makeRow(it);
      tbody.appendChild(tr);
      bindRow(tr);
    }
    search.value = ''; renderPick();
    compute();
  }
  function compute() {
    const rows = [...document.querySelectorAll('#items tr.sli')];
    let total = 0, totalmin = 0;
    for (const tr of rows) {
      const d = tr.querySelector('.deptv').value;
      const c = tr.querySelector('.cat').value, f = tr.querySelector('.formv').value;
      const info = ROWS[key(d,c,f)];
      if (!info) continue;
      const sel = tr.querySelector('select.src');
      const src = info.sources.find(s => s.slug === sel.value) || info.sources[0];
      const qty = parseFloat(tr.querySelector('input.qty').value) || 1;
      total += (src ? src.price : 0) * qty;
      totalmin += (info.sources[0] ? info.sources[0].price : 0) * qty;
      const det = tr.querySelector('.detail');
      if (det) {
        const parts = [];
        if (src && src.store) parts.push(src.store);
        if (src && src.sample) parts.push(src.sample);
        det.textContent = parts.join(' · ');
      }
      const priceEl = tr.querySelector('.price');
      if (priceEl) {
        const pkg = info.sources.find(s => s.slug === sel.value) || info.sources[0];
        priceEl.innerHTML = src
          ? '<b>' + fmt(src.price * qty) + '</b><span class="pkg">' + fmt(pkg ? pkg.price : src.price) + '/' + info.unit + '</span>'
          : '—';
      }
    }
    document.getElementById('total').textContent = fmt(total);
    document.getElementById('totalmin').textContent = fmt(totalmin);
    if (empty) empty.style.display = rows.length ? 'none' : 'block';
    if (tableEl) tableEl.style.display = rows.length ? '' : 'none';
  }
  async function persist(id, payload) {
    try {
      await fetch('/shopping-lists/items/' + id, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
    } catch (e) {}
  }
  for (const tr of [...document.querySelectorAll('#items tr.sli')]) bindRow(tr);
  compute();
  renderPick();
})();
</script>"""
    return (
        template.replace("@@LIST_ID@@", str(list_id)).replace("@@ROWS@@", rows_json)
    )
