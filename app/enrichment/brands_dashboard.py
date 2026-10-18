"""Brand dictionary screen, modeled on the category editor."""

from __future__ import annotations

from html import escape
from typing import Any


def _br(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def render_brands_page(data: dict[str, Any]) -> str:
    rows: list[str] = []
    for row in data["rows"]:
        rows.append(
            "<tr>"
            "<td class='pick'><input type='checkbox' class='pick' "
            f"data-key='{escape(row['key'])}' data-name='{escape(row['name'])}' "
            f"aria-label='Selecionar {escape(row['name'])}'></td>"
            f"<td class='raw'>{escape(row['name'])}</td>"
            f"<td class='n'>{_br(row['items'])}</td>"
            f"<td class='n'>{_br(row['retailers'])}</td>"
            f"<td><span class='st {escape(row['status'])}'>{escape(row['status_label'])}</span></td>"
            f"<td class='sample'>{escape(row['sample'])}</td>"
            "<td class='acts'>"
            f"<button type='button' data-action='approve' data-key='{escape(row['key'])}' "
            f"data-name='{escape(row['name'])}'>Aprovar</button>"
            f"<button type='button' data-action='block' data-key='{escape(row['key'])}' "
            f"data-name='{escape(row['name'])}'>Bloquear</button>"
            f"<input class='alias' placeholder='Apelido de…' data-key='{escape(row['key'])}' "
            f"data-name='{escape(row['name'])}'>"
            "<button type='button' class='link-alias'>Vincular</button>"
            "</td></tr>"
        )
    table = (
        "<div class='table-wrap'><table><thead><tr>"
        "<th class='pick'><input type='checkbox' id='pick-all' aria-label='Selecionar todas'></th>"
        "<th>Marca</th><th>Itens</th><th>Redes</th><th>Situação</th><th>Exemplo</th><th></th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        if rows
        else "<div class='review-empty'>Nenhuma marca para este filtro.</div>"
    )
    query = escape(data.get("q") or "")
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Dicionário de marcas</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.cat-tools{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}}
.review-search{{flex:1 1 240px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px}}
.review-search input{{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px}}
.review-empty{{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted)}}
.raw{{font-weight:700}}
td.n{{color:var(--muted);text-align:center}}
td.sample{{color:#51615a;font-size:12px;max-width:280px}}
td.acts{{white-space:nowrap}}
td.pick,th.pick{{width:36px;text-align:center}}
td.pick input,th.pick input{{width:16px;height:16px;cursor:pointer}}
#approve-selected:disabled{{opacity:.45;cursor:default}}
td.acts button,.newbrand button,#approve-selected{{padding:7px 10px;border:1px solid var(--line);border-radius:9px;background:#fff;font-size:12px;font-weight:700;cursor:pointer}}
td.acts input,.newbrand input{{padding:7px 10px;border:1px solid var(--line);border-radius:9px;font-size:12px;width:140px}}
.st{{font-size:11px;font-weight:750;padding:3px 8px;border-radius:99px;background:#f1f3f2;color:var(--muted)}}
.st.approved{{background:#eaf9f1;color:#067647}}
.st.blocked{{background:#fff0ee;color:#b42318}}
.st.alias{{background:#eaf2ff;color:#175cd3}}
.msg{{display:none;padding:10px 14px;border-radius:10px;margin-bottom:12px;background:#eaf9f1;color:#067647}}
.msg.err{{background:#fff0ee;color:#b42318}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Marcas</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Dicionário">
<a href="/catalog">Catálogo</a>
<a href="/catalog/categories">Categorias</a>
<a class="active" href="/catalog/brands">Marcas</a>
<a href="/catalog/butcher-review">Revisão</a>
</nav>
<section class="hero"><div><span class="eyebrow">Dicionário</span>
<h1>Marcas</h1>
<p>{_br(data['inferred_total'])} marcas foram só inferidas do título.
Esta lista mostra {data['shown']}. Aprovar, bloquear e vincular gravam o
dicionário ({_br(data['decisions'])} decisões salvas). O normalizador
{escape(data['normalizer_version'])} ainda não lê essas tabelas, então as
linhas já calculadas ficam como estão.</p></div></section>
<div id="msg" class="msg"></div>
<form class="cat-tools" method="get" action="/catalog/brands">
<div class="review-search"><input name="q" value="{query}" placeholder="Buscar marca…"></div>
<button class="page-button" type="submit">Buscar</button>
<button id="approve-selected" type="button" disabled>Aprovar selecionados</button>
<span class="newbrand"><input id="new-name" placeholder="Nova marca…">
<button id="new-approve" type="button">Aprovar nova</button></span>
</form>
<div id="list">{table}</div>
</main>
<script>
(function(){{
  async function send(body){{
    const msg=document.getElementById('msg');
    try{{
      const res=await fetch('/catalog/brands',{{
        method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify(body)
      }});
      const data=await res.json();
      msg.className='msg'+(res.ok?'':' err');
      msg.style.display='block';
      msg.textContent=res.ok?'Salvo. Recarregando…':(data.detail||'Erro ao salvar');
      if(res.ok) setTimeout(()=>location.reload(),500);
    }}catch(e){{
      msg.className='msg err'; msg.style.display='block'; msg.textContent='Falha ao salvar';
    }}
  }}
  const bulk=document.getElementById('approve-selected');
  function picks(){{ return [...document.querySelectorAll('#list input.pick')]; }}
  function refresh(){{
    const marked=picks().filter(el=>el.checked);
    bulk.disabled=marked.length===0;
    bulk.textContent=marked.length?`Aprovar selecionados (${{marked.length}})`:'Aprovar selecionados';
    const all=document.getElementById('pick-all');
    if(all) all.checked=marked.length>0 && marked.length===picks().length;
  }}
  const all=document.getElementById('pick-all');
  if(all) all.addEventListener('change',function(){{
    picks().forEach(el=>{{ el.checked=all.checked; }});
    refresh();
  }});
  document.getElementById('list').addEventListener('change',function(ev){{
    if(ev.target.classList && ev.target.classList.contains('pick')) refresh();
  }});
  bulk.addEventListener('click',function(){{
    const items=picks().filter(el=>el.checked).map(el=>({{key:el.dataset.key,name:el.dataset.name}}));
    if(items.length) send({{action:'approve_selected',items}});
  }});
  document.getElementById('list').addEventListener('click',function(ev){{
    const btn=ev.target.closest('button');
    if(!btn) return;
    if(btn.classList.contains('link-alias')){{
      const input=btn.parentElement.querySelector('input.alias');
      send({{action:'alias',key:input.dataset.key,name:input.dataset.name,target:input.value}});
      return;
    }}
    send({{action:btn.dataset.action,key:btn.dataset.key,name:btn.dataset.name}});
  }});
  document.getElementById('new-approve').addEventListener('click',function(){{
    const name=document.getElementById('new-name').value.trim();
    if(name) send({{action:'approve',name:name}});
  }});
}})();
</script>
</body></html>"""
