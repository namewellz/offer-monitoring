from datetime import UTC, datetime
from html import escape
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.annotation.detector import propose_regions
from app.annotation.schemas import RegionSet
from app.core.config import get_settings
from app.db.models import (
    Flyer,
    FlyerPage,
    OfferRegionAnnotation,
    Retailer,
    Store,
)
from app.db.session import get_db

router = APIRouter(prefix="/annotation", tags=["annotation"])


def _page(db: Session, page_id: UUID) -> FlyerPage:
    page = db.get(FlyerPage, page_id)
    if page is None:
        raise HTTPException(404, "Page not found")
    return page


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def annotation_index(db: Session = Depends(get_db)):
    rows = db.execute(
        select(FlyerPage, Flyer, Store, Retailer)
        .join(Flyer, FlyerPage.flyer_id == Flyer.id)
        .join(Store, Flyer.store_id == Store.id)
        .join(Retailer, Store.retailer_id == Retailer.id)
        .order_by(Flyer.created_at.desc(), FlyerPage.page_number)
    ).all()
    body = []
    for page, flyer, store, retailer in rows:
        count = len(
            db.scalars(
                select(OfferRegionAnnotation).where(OfferRegionAnnotation.page_id == page.id)
            ).all()
        )
        body.append(
            "<tr>"
            f"<td>{escape(retailer.name)}</td><td>{escape(store.name)}</td>"
            f"<td>{page.page_number}</td><td>{count}</td><td>{escape(page.annotation_status)}</td>"
            f'<td><a href="/annotation/pages/{page.id}">Anotar</a></td></tr>'
        )
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Anotações de ofertas</title>
<style>body{{font-family:system-ui;margin:0;background:#f4f6f8;color:#17202a}}main{{max-width:1050px;margin:36px auto;padding:0 18px}}
table{{width:100%;border-collapse:collapse;background:white;box-shadow:0 2px 14px #0001}}th,td{{padding:13px;border-bottom:1px solid #e8ecef;text-align:left}}
th{{background:#eaf6ef}}a{{color:#087443;font-weight:650}}.actions{{margin:20px 0}}</style></head>
<body><main><h1>Dataset de ofertas</h1><p>Corrija as sugestões e aprove apenas caixas completas.</p>
<div class="actions"><a href="/annotation/export/coco">Exportar COCO aprovado</a></div>
<table><thead><tr><th>Supermercado</th><th>Loja</th><th>Página</th><th>Caixas</th><th>Status</th><th></th></tr></thead>
<tbody>{''.join(body)}</tbody></table></main></body></html>"""


EDITOR_HTML = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Anotar ofertas</title><style>
*{box-sizing:border-box}body{font-family:system-ui;margin:0;background:#121820;color:#eef3f6}header{position:sticky;top:0;z-index:4;background:#19222d;padding:10px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 12px #0008}
button,a{padding:9px 13px;border:0;border-radius:7px;background:#2a3948;color:white;text-decoration:none;cursor:pointer;font-weight:650}button.primary{background:#087443}button.approve{background:#16a34a}button.danger{background:#b42318}.status{margin-left:auto;color:#a9bbc8}.layout{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:14px;padding:14px}.stage{position:relative;margin:auto;width:min(100%,900px)}#page{display:block;width:100%;height:auto}#overlay{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:crosshair}.sidebar{background:#19222d;padding:14px;border-radius:10px;height:max-content;position:sticky;top:76px}.sidebar code{color:#6ee7a7}.help{font-size:13px;line-height:1.45;color:#b9c7d1}#list{max-height:60vh;overflow:auto}.region{padding:7px;border-bottom:1px solid #30404e;cursor:pointer}.region.active{background:#087443}@media(max-width:850px){.layout{grid-template-columns:1fr}.sidebar{position:static}}
</style></head><body><header><a href="/annotation">← Páginas</a><button id="suggest">Sugerir com OpenCV</button><button id="save" class="primary">Salvar</button><button id="approve" class="approve">Aprovar página</button><button id="remove" class="danger">Excluir selecionada</button><span class="status" id="status">Carregando…</span></header>
<div class="layout"><div class="stage"><img id="page" src="/pages/__PAGE_ID__/image"><canvas id="overlay"></canvas></div><aside class="sidebar"><h3>Caixas: <span id="count">0</span></h3><p class="help">Arraste no vazio para criar. Arraste dentro da caixa para mover. Arraste o canto inferior direito para redimensionar. Cada caixa deve conter produto, nome, preço e condição.</p><div id="list"></div></aside></div>
<script>
const pageId='__PAGE_ID__', img=document.querySelector('#page'), canvas=document.querySelector('#overlay'), ctx=canvas.getContext('2d');
let regions=[], selected=-1, action=null, start=null, original=null;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function point(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)/r.width*1000,y:(e.clientY-r.top)/r.height*1000}}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);const sx=canvas.width/1000,sy=canvas.height/1000;regions.forEach((b,i)=>{ctx.strokeStyle=i===selected?'#facc15':'#39ff14';ctx.lineWidth=Math.max(3,canvas.width/260);ctx.strokeRect(b.x*sx,b.y*sy,b.width*sx,b.height*sy);ctx.fillStyle=i===selected?'#ca8a04':'#15951b';ctx.fillRect(b.x*sx,b.y*sy,34*sx,25*sy);ctx.fillStyle='white';ctx.font=`bold ${Math.max(14,canvas.width/48)}px system-ui`;ctx.fillText(String(i+1),b.x*sx+4,b.y*sy+20*sy);if(i===selected){ctx.fillStyle='#facc15';ctx.fillRect((b.x+b.width)*sx-8,(b.y+b.height)*sy-8,16,16)}});renderList()}
function renderList(){document.querySelector('#count').textContent=regions.length;document.querySelector('#list').innerHTML=regions.map((b,i)=>`<div class="region ${i===selected?'active':''}" data-i="${i}">#${i+1} · ${b.source||'MANUAL'}<br><code>${b.x}, ${b.y}, ${b.width}×${b.height}</code></div>`).join('');document.querySelectorAll('.region').forEach(el=>el.onclick=()=>{selected=Number(el.dataset.i);draw()})}
img.onload=()=>{canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;load()};
async function load(){const data=await fetch(`/annotation/pages/${pageId}/regions`).then(r=>r.json());regions=data.regions;document.querySelector('#status').textContent=data.status;draw()}
canvas.onpointerdown=e=>{canvas.setPointerCapture(e.pointerId);const p=point(e);selected=-1;for(let i=regions.length-1;i>=0;i--){const b=regions[i],inside=p.x>=b.x&&p.x<=b.x+b.width&&p.y>=b.y&&p.y<=b.y+b.height;if(inside){selected=i;action=(Math.abs(p.x-(b.x+b.width))<25&&Math.abs(p.y-(b.y+b.height))<25)?'resize':'move';start=p;original={...b};break}}if(selected<0){regions.push({x:Math.round(p.x),y:Math.round(p.y),width:1,height:1,source:'MANUAL',confidence:null});selected=regions.length-1;action='create';start=p}draw()};
canvas.onpointermove=e=>{if(!action)return;const p=point(e),b=regions[selected];b.source=action==='create'?'MANUAL':'MANUAL_EDITED';b.confidence=null;if(action==='create'){b.x=Math.round(Math.min(start.x,p.x));b.y=Math.round(Math.min(start.y,p.y));b.width=Math.round(Math.abs(p.x-start.x));b.height=Math.round(Math.abs(p.y-start.y))}else if(action==='move'){b.x=Math.round(clamp(original.x+p.x-start.x,0,1000-original.width));b.y=Math.round(clamp(original.y+p.y-start.y,0,1000-original.height))}else{b.width=Math.round(clamp(original.width+p.x-start.x,5,1000-original.x));b.height=Math.round(clamp(original.height+p.y-start.y,5,1000-original.y))}draw()};
canvas.onpointerup=()=>{if(action==='create'&&(regions[selected].width<8||regions[selected].height<8)){regions.splice(selected,1);selected=-1}action=null;draw()};
document.querySelector('#remove').onclick=()=>{if(selected>=0){regions.splice(selected,1);selected=-1;draw()}};
async function save(){const response=await fetch(`/annotation/pages/${pageId}/regions`,{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify({regions})});if(!response.ok)throw new Error(await response.text());const data=await response.json();document.querySelector('#status').textContent=data.status;await load()}
document.querySelector('#save').onclick=()=>save().catch(e=>alert(e));
document.querySelector('#suggest').onclick=async()=>{document.querySelector('#status').textContent='Detectando…';const r=await fetch(`/annotation/pages/${pageId}/preannotate`,{method:'POST'});if(!r.ok)return alert(await r.text());await load()};
document.querySelector('#approve').onclick=async()=>{await save();const r=await fetch(`/annotation/pages/${pageId}/approve`,{method:'POST'});if(!r.ok)return alert(await r.text());await load()};
</script></body></html>"""


@router.get("/pages/{page_id}", response_class=HTMLResponse, include_in_schema=False)
def annotation_editor(page_id: UUID, db: Session = Depends(get_db)):
    _page(db, page_id)
    return EDITOR_HTML.replace("__PAGE_ID__", str(page_id))


@router.get("/pages/{page_id}/regions")
def annotation_regions(page_id: UUID, db: Session = Depends(get_db)):
    page = _page(db, page_id)
    rows = db.scalars(
        select(OfferRegionAnnotation)
        .where(OfferRegionAnnotation.page_id == page.id)
        .order_by(OfferRegionAnnotation.sequence)
    ).all()
    return {
        "page_id": page.id,
        "status": page.annotation_status,
        "regions": [
            {
                "x": row.x,
                "y": row.y,
                "width": row.width,
                "height": row.height,
                "source": row.source,
                "confidence": row.confidence,
            }
            for row in rows
        ],
    }


@router.put("/pages/{page_id}/regions")
def replace_annotation_regions(
    page_id: UUID, payload: RegionSet, db: Session = Depends(get_db)
):
    page = _page(db, page_id)
    db.execute(delete(OfferRegionAnnotation).where(OfferRegionAnnotation.page_id == page.id))
    db.add_all(
        [
            OfferRegionAnnotation(
                page_id=page.id,
                sequence=index,
                x=region.x,
                y=region.y,
                width=region.width,
                height=region.height,
                source=region.source,
                confidence=region.confidence,
                approved=False,
            )
            for index, region in enumerate(payload.regions, start=1)
        ]
    )
    page.annotation_status = "IN_REVIEW"
    page.annotated_at = None
    db.commit()
    return {"status": page.annotation_status, "regions": len(payload.regions)}


@router.post("/pages/{page_id}/preannotate")
def preannotate_page(page_id: UUID, db: Session = Depends(get_db)):
    page = _page(db, page_id)
    path = Path(page.local_path).resolve()
    storage = get_settings().flyer_storage_path.resolve()
    if not path.is_relative_to(storage) or not path.is_file():
        raise HTTPException(404, "Page image not found")
    proposed = propose_regions(str(path))
    db.execute(delete(OfferRegionAnnotation).where(OfferRegionAnnotation.page_id == page.id))
    db.add_all(
        [
            OfferRegionAnnotation(page_id=page.id, sequence=index, approved=False, **region)
            for index, region in enumerate(proposed, start=1)
        ]
    )
    page.annotation_status = "IN_REVIEW"
    page.annotated_at = None
    db.commit()
    return {"status": page.annotation_status, "regions": len(proposed)}


@router.post("/pages/{page_id}/approve")
def approve_annotations(page_id: UUID, db: Session = Depends(get_db)):
    page = _page(db, page_id)
    rows = db.scalars(
        select(OfferRegionAnnotation).where(OfferRegionAnnotation.page_id == page.id)
    ).all()
    if not rows:
        raise HTTPException(409, "Cannot approve a page without regions")
    for row in rows:
        row.approved = True
    page.annotation_status = "APPROVED"
    page.annotated_at = datetime.now(UTC)
    db.commit()
    return {"status": page.annotation_status, "regions": len(rows)}


@router.get("/export/coco")
def export_coco(db: Session = Depends(get_db)):
    pages = db.scalars(
        select(FlyerPage)
        .where(FlyerPage.annotation_status == "APPROVED")
        .order_by(FlyerPage.created_at, FlyerPage.page_number)
    ).all()
    images = []
    annotations = []
    annotation_id = 1
    for image_id, page in enumerate(pages, start=1):
        images.append(
            {
                "id": image_id,
                "file_name": Path(page.local_path).name,
                "width": page.width,
                "height": page.height,
                "page_id": str(page.id),
            }
        )
        rows = db.scalars(
            select(OfferRegionAnnotation)
            .where(
                OfferRegionAnnotation.page_id == page.id,
                OfferRegionAnnotation.approved.is_(True),
            )
            .order_by(OfferRegionAnnotation.sequence)
        ).all()
        for row in rows:
            x = round(row.x * page.width / 1000, 2)
            y = round(row.y * page.height / 1000, 2)
            width = round(row.width * page.width / 1000, 2)
            height = round(row.height * page.height / 1000, 2)
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": 1,
                    "bbox": [x, y, width, height],
                    "area": round(width * height, 2),
                    "iscrowd": 0,
                    "source": row.source,
                }
            )
            annotation_id += 1
    return {
        "info": {"description": "Offer block annotations", "version": "1.0"},
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": "offer_block"}],
    }
