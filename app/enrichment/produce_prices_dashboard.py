"""Server-rendered "onde comprar mais barato" screen for Hortifrúti products.

Each row is a canonical produce product (identity decoupled from the sale
presentation, ex.: "Maçã Fuji"). Prices across every presentation of that
product (kg / bandeja / pacote / unidade) are normalized to R$/kg and per
retailer the best store is shown, so the top of each row answers: where to buy
this product cheapest.
"""

from __future__ import annotations

from html import escape
from typing import Any

from app.enrichment.dashboard import RETAILER_LABELS


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def render_produce_prices_page(payload: dict[str, Any]) -> str:
    identities = payload["identities"]
    modeled = sum(item["products"] for item in identities)

    rows: list[str] = []
    for item in identities:
        best = item["best"]
        if best:
            best_price = f"{_brl(best['per_kg'])}/kg"
            best_who = RETAILER_LABELS.get(best["label"], best["label"])
        else:
            best_price = "—"
            best_who = ""
        retailer_lines: list[str] = []
        for i, source in enumerate(item["retailers"]):
            is_best = i == 0 and item["has_kg"]
            price = _brl(source["per_kg"]) + "/kg"
            detail = " · ".join(
                part
                for part in (
                    RETAILER_LABELS.get(source["label"], source["label"]),
                    source["store"] or "",
                    source["presentation"] or source["sample"] or "",
                )
                if part
            )
            retailer_lines.append(
                "<li"
                + (" class='best'" if is_best else "")
                + ">"
                + ("<b>✓ mais barato:</b> " if is_best else "")
                + f"<span class='p'>{escape(price)}</span>"
                + f"<span class='d'>{escape(detail)}</span></li>"
            )
        for source in item["unit_only"]:
            price = _brl(source["price"]) + "/" + (source["presentation"] or "un")
            detail = " · ".join(
                part
                for part in (
                    RETAILER_LABELS.get(source["label"], source["label"]),
                    source["store"] or "",
                    source["sample"] or "",
                )
                if part
            )
            retailer_lines.append(
                "<li><span class='p'>" + escape(price) + "</span>"
                f"<span class='d'>{escape(detail)}</span></li>"
            )
        src_html = "".join(retailer_lines) or "<li class='d'>sem preço</li>"

        variety_chip = (
            f"<span class='variety'>{escape(item['variety'])}</span>" if item["variety"] else ""
        )
        rows.append(
            "<details class='pr-row'><summary>"
            "<span class='name'>" + escape(item["product"]) + variety_chip + "</span>"
            f"<span class='n'>{item['products']} produtos</span>"
            f"<span class='best'>{escape(best_price)} <i>· {escape(best_who)}</i></span>"
            "</summary><ul class='srcs'>" + src_html + "</ul></details>"
        )

    body = "".join(rows) or (
        "<div class='empty'>Nenhum produto de hortifrúti modelado com preço "
        "neste departamento ainda.</div>"
    )

    chips = (
        "<div class='tools'>"
        f"<span class='chip-stat'><b>{_num(len(identities))}</b> produtos (identidade)</span>"
        f"<span class='chip-stat'><b>{_num(modeled)}</b> produtos-fonte agrupados</span>"
        f"<span class='chip-stat'><b>{_num(payload['samples'])}</b> ofertas lidas</span>"
        f"<span class='chip-stat'><b>{_num(payload['unmodeled'])}</b> ofertas sem modelo</span>"
        "</div>"
    )

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#145c42"><title>Hortifrúti — onde comprar mais barato</title>
<link rel="stylesheet" href="/static/catalog.css?v=20260829-4">
<style>
.tools{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:14px}}
.chip-stat{{font-size:12px;color:var(--muted)}}.chip-stat b{{font-size:16px;color:var(--green);display:block}}
.sbox{{flex:1 1 260px;display:flex;align-items:center;border:1px solid var(--line);border-radius:11px;padding:2px 4px 2px 12px;background:#fff}}
.sbox input{{border:0;outline:0;width:100%;padding:10px 6px;font-size:14px;background:transparent}}
.filterrow{{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--muted);white-space:nowrap}}
.filterrow label{{display:flex;gap:5px;align-items:center;cursor:pointer}}
.pr-row{{background:#fff;border:1px solid var(--line);border-radius:14px;margin-bottom:8px;overflow:hidden}}
.pr-row>summary{{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 14px}}
.pr-row>summary::-webkit-details-marker{{display:none}}
.pr-row>summary:hover{{background:#fbfdfc}}
.pr-row[open]>summary{{border-bottom:1px solid var(--line)}}
.pr-row .name{{font-weight:700;font-size:14.5px;flex:1 1 170px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.pr-row .variety{{font-size:10px;color:#8a5a00;background:#fff4df;border:1px solid #f3dfb6;border-radius:99px;padding:1px 7px;font-weight:800}}
.pr-row .n{{font-size:11px;color:var(--muted)}}
.pr-row .best{{font-size:13px;color:#067647;font-weight:800;white-space:nowrap}}
.pr-row .best i{{font-style:normal;color:var(--muted);font-weight:600;font-size:12px}}
ul.srcs{{list-style:none;margin:0;padding:8px 14px 12px}}
ul.srcs li{{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;padding:4px 0;font-size:13px}}
ul.srcs li .p{{font-weight:800;color:var(--green);min-width:120px}}
ul.srcs li .d{{color:#51615a;font-size:12px}}
ul.srcs li.best{{background:#eaf9f1;border-radius:8px;padding:6px 8px;margin-left:-8px}}
.empty{{background:#fff;border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted)}}
.hint{{background:#eef6f1;border:1px solid #d7eadf;border-radius:12px;padding:10px 14px;font-size:12.5px;color:#2f6b4f;margin-bottom:12px}}
.hint b{{color:#145c42}}
</style></head><body>
<header class="topbar"><div class="shell brandbar">
<a class="brand" href="/catalog"><span class="brand-mark">OM</span><span>Offer Monitor</span></a>
<span class="live"><i></i> Hortifrúti · produto</span></div></header>
<main class="shell">
<nav class="view-tabs" aria-label="Visões">
<a class="active" href="/catalog/produce-prices">Onde comprar mais barato</a>
<a href="/catalog/dept-prices?department=Hortifruti">Por unidade</a>
<a href="/catalog/department-review?department=Hortifruti">Revisão</a>
<a href="/catalog/categories?department=Hortifruti">Categorias</a>
<a href="/shopping-lists">Lista</a>
</nav>
<section class="hero"><div><span class="eyebrow">Hortifrúti · identidade de produto</span>
<h1>Onde comprar cada produto mais barato</h1>
<p>O produto é a identidade — <b>“Maçã Fuji”</b> — e a forma de venda (kg,
bandeja, pacote, unidade) não muda o produto: cada oferta é normalizada para
<b>R$/kg</b> e o melhor preço por rede é mantido. O topo de cada linha diz onde
comprar aquele produto mais barato.</p></div></section>
{chips}
<div class="hint">Ex.: <b>Maçã Fuji</b> reúne “Maçã Fuji Kg”, “Maçã Fuji Bandeja 600g”,
“Maçã Nacional Fuji 17kg”… e mostra a rede mais barata entre todas as formas de venda.</div>
<div class="tools">
<div class="sbox"><input id="q" type="search" placeholder="Filtrar produto…"></div>
<span class="filterrow"><label><input id="onlyvar" type="checkbox">só com variedade</label></span>
</div>
<div id="list">{body}</div>
</main>
<script>
(function(){{
  const q=document.getElementById('q');
  const onlyvar=document.getElementById('onlyvar');
  const rows=[...document.querySelectorAll('#list details.pr-row')];
  const fold=s=>(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  function apply(){{
    const t=fold(q.value);
    for(const r of rows){{
      const text=fold(r.textContent);
      const variety=r.querySelector('.variety')!==null;
      let show=(!t||text.includes(t))&&(!onlyvar.checked||variety);
      r.style.display=show?'':'none';
    }}
  }}
  q.addEventListener('input',apply);
  onlyvar.addEventListener('change',apply);
}})();
</script>
</body></html>"""
