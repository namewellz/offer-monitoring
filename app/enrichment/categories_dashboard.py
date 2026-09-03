"""Server-rendered screen to edit/merge LLM category names (canonical labels).

Each raw label the LLM produced is listed with how many products use it. You can
rename it (type a new name) or merge several into one (type the same canonical
for them, e.g. "Acém" for "Acém", "Acém Bovino", "Acém em Cubos"). Saving writes
to ``llm_category_labels`` and the price screen regroups by canonical.
"""

from __future__ import annotations

from html import escape
from typing import Any


def render_categories_page(
    labels: list[dict[str, Any]],
    base: tuple[str, ...],
    canonicals: list[str] | None = None,
) -> str:
    options = sorted({name for name in (*base, *(canonicals or [])) if name})
    rows: list[str] = []
    for row in labels:
        label = row["label"]
        rows.append(
            "<tr>"
            f'<td class="raw">{escape(label)}</td>'
            f'<td class="n">{row["count"]}</td>'
            f'<td><input class="canon" list="canonical-list" '
            f'data-label="{escape(label)}" value="{escape(row.get("canonical") or label)}"></td>'
            "</tr>"
        )
    table = (
        '<div class="table-wrap"><table>'
        "<thead><tr><th>Categoria (como a LLM retornou)</th><th>Itens</th>"
        "<th>Nome canônico (edite/merge)</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    datalist = "".join(f'<option value="{escape(name)}"></option>' for name in options)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Açougue — categorias canônicas</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<datalist id="canonical-list">{datalist}</datalist>
<style>
.cat-tools{{display:flex;gap:10px;align-items:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}}
.review-search{{flex:1 1 240px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px}}
.review-search input{{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px}}
.review-empty{{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted)}}
.raw{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}}
td.n{{color:var(--muted);text-align:center}}
input.canon{{width:min(320px,100%);padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px}}
.msg{{display:none;padding:10px 14px;border-radius:10px;margin-bottom:12px;background:#eaf9f1;color:#067647}}
.msg.err{{background:#fff0ee;color:var(--red)}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Açougue</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões do Açougue">
<a href="/catalog/cuts">Comparativo R$/kg</a>
<a href="/catalog/butcher-review">Revisão de classificação</a>
<a class="active" href="/catalog/categories">Categorias</a>
</nav>
<section class="hero"><div><span class="eyebrow">Vocabulário canônico</span>
<h1>Categorias canônicas</h1>
<p>{len(labels)} categorias em uso. Edite o nome para corrigir, ou repita o mesmo
nome canônico em várias linhas para agrupá-las (ex.: juntar 'Acém Bovino' em
'Acém'). Use o atalho ou digite livre — salva e a tela de preço regrupa.</p></div></section>
<div id="msg" class="msg"></div>
<div class="cat-tools">
<div class="review-search"><input id="q" type="search" placeholder="Filtrar categoria…"></div>
<span style="display:flex;gap:6px;align-items:center">
<input id="newcat" list="canonical-list" placeholder="Nova categoria canônica…" style="padding:8px 10px;border:1px solid var(--line);border-radius:9px;font-size:13px">
<button class="page-button" id="addcat" type="button" style="background:var(--mint)">+ Adicionar</button>
</span>
<button class="page-button" id="save" type="button" style="background:var(--green);color:#fff">Salvar</button>
</div>
<div id="list">{table or '<div class="review-empty">Nenhuma categoria ainda.</div>'}</div>
</main>
<script>
(function(){{
  const q=document.getElementById('q');
  const rows=[...document.querySelectorAll('#list tbody tr')];
  q.addEventListener('input',function(){{
    const t=q.value.trim().toLowerCase();
    for(const r of rows) r.style.display=(!t||(r.textContent||'').toLowerCase().includes(t))?'':'none';
  }});
  document.getElementById('save').addEventListener('click',async function(){{
    const updates=[...document.querySelectorAll('input.canon')].map(inp=>({{
      label: inp.dataset.label,
      canonical: inp.value.trim() || inp.dataset.label
    }}));
    await doSave(updates);
  }});
  document.getElementById('addcat').addEventListener('click',async function(){{
    const name=document.getElementById('newcat').value.trim();
    if(!name) return;
    await doSave([{{label:name, canonical:name}}]);
  }});
  async function doSave(updates){{
    const btn=document.getElementById('save'); btn.disabled=true;
    try{{
      const res=await fetch('/catalog/categories',{{
        method:'POST',headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{updates}})
      }});
      const data=await res.json();
      const msg=document.getElementById('msg');
      msg.className='msg'+(res.ok?'':' err');
      msg.style.display='block';
      msg.textContent=res.ok?('Salvo: '+data.created+' novas, '+data.updated+' alteradas. Recarregando…'):('Erro: '+JSON.stringify(data));
      if(res.ok) setTimeout(()=>location.reload(),600);
    }}catch(e){{
      const msg=document.getElementById('msg'); msg.className='msg err'; msg.style.display='block';
      msg.textContent='Falha ao salvar: '+e;
    }}finally{{ btn.disabled=false; }}
  }}
}})();
</script>
</body></html>"""
