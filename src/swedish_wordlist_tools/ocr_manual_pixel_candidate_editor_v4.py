from __future__ import annotations

import argparse
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageOps


def _data_uri_with_margin(path: Path, margin: int) -> tuple[str, int, int]:
    with Image.open(path) as im0:
        im = im0.convert("L")
        framed = ImageOps.expand(im, border=margin, fill=255)
        buf = io.BytesIO()
        framed.save(buf, format="PNG")
    return (
        "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
        framed.width,
        framed.height,
    )


def _ink_mask(path: Path, threshold: int) -> list[list[int]]:
    with Image.open(path) as im0:
        im = im0.convert("L")
        return [
            [1 if im.getpixel((x, y)) < threshold else 0 for x in range(im.width)]
            for y in range(im.height)
        ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Correct auto-proposed pixel candidates with DOM grid, box and pixel modes.")
    ap.add_argument("matches", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=18)
    ap.add_argument("--margin", type=int, default=2)
    ap.add_argument("--ink-threshold", type=int, default=210)
    args = ap.parse_args()

    payload = json.loads(args.matches.read_text(encoding="utf-8"))
    scale = max(8, args.scale)
    margin = max(0, args.margin)
    cards: list[str] = []

    for word in payload.get("results", []):
        if not isinstance(word, dict):
            continue
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not rel or not path.exists():
            continue
        uri, fw, fh = _data_uri_with_margin(path, margin)
        ink = _ink_mask(path, args.ink_threshold)
        proposals: list[dict[str, object]] = []
        for status, key in (("accepted", "matches"), ("topology-rejected", "rejected_candidates")):
            for label, hits in (word.get(key) or {}).items():
                for hit in hits:
                    proposals.append({
                        "label": label,
                        "status": status,
                        "pixels": hit.get("matched_pixels", []),
                        "contacts": hit.get("external_contact_pixels", []),
                        "external_contacts": hit.get("external_contacts", 0),
                        "missing": hit.get("missing", 0),
                        "extra": hit.get("extra", 0),
                    })

        cards.append(f'''<article class="card"
 data-source-id="{html.escape(str(word.get('source_id') or ''), quote=True)}"
 data-style="{html.escape(str(word.get('style') or ''), quote=True)}"
 data-expected="{html.escape(str(word.get('expected_word') or ''), quote=True)}"
 data-headword="{html.escape(str(word.get('headword') or ''), quote=True)}"
 data-page="{html.escape(str(word.get('page') or ''), quote=True)}"
 data-subnr="{html.escape(str(word.get('subnr') or ''), quote=True)}"
 data-word-file="{html.escape(rel, quote=True)}"
 data-w="{int(word.get('width') or 0)}" data-h="{int(word.get('height') or 0)}"
 data-fw="{fw}" data-fh="{fh}" data-baseline="{int(word.get('baseline_y') or 0)}"
 data-ink='{html.escape(json.dumps(ink), quote=True)}'
 data-proposals='{html.escape(json.dumps(proposals, ensure_ascii=False), quote=True)}'>
<header><strong>{html.escape(str(word.get('expected_word') or ''))}</strong>
<span class="badge">{html.escape(str(word.get('style') or ''))}</span>
<span>uppslagsord: <b>{html.escape(str(word.get('headword') or '')) or '(saknas)'}</b></span>
<span>sida {html.escape(str(word.get('page') or ''))} · subnr {html.escape(str(word.get('subnr') or ''))}</span></header>
<div class="controls">
<label>Etikett <input class="label" size="8"></label>
<button class="boxmode active" type="button">Boxläge</button>
<button class="pixelmode" type="button">Pixelläge</button>
<label>Baslinje y=<input class="baseline" type="number" value="{int(word.get('baseline_y') or 0)}"></label>
<button class="up" type="button">−1</button><button class="down" type="button">+1</button>
<button class="delete" type="button">Ta bort valt förslag</button>
<button class="new" type="button">Nytt förslag</button>
<button class="clear" type="button">Rensa ordet</button>
<span class="imginfo">bild {fw}×{fh}</span>
</div>
<div class="stack" style="width:{fw*scale}px;height:{fh*scale}px">
<img class="src" src="{uri}" width="{fw*scale}" height="{fh*scale}" alt="">
<div class="grid" style="grid-template-columns:repeat({fw},{scale}px);grid-template-rows:repeat({fh},{scale}px)"></div>
<div class="selection-box"></div>
<div class="baseline-line"></div>
</div>
<div class="proposal-list"></div><div class="legend"></div>
</article>''')

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL candidate editor v4</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui;margin:20px;background:#f3f3f3;color:#171717}}
.toolbar{{position:sticky;top:0;z-index:20;background:#f3f3f3ee;padding:8px 0}}
.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:10px;margin:12px 0}}
header,.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}
header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px}}
input,button{{font:inherit}}.active{{font-weight:800;outline:2px solid #1479ff}}
.stack{{position:relative;display:block;overflow:hidden;border:1px solid #999;background:white;user-select:none}}
.stack img{{position:absolute;left:0;top:0;display:block;image-rendering:pixelated;z-index:1;pointer-events:none}}
.grid{{position:absolute;left:0;top:0;display:grid;z-index:3}}
.cell{{width:{scale}px;height:{scale}px;border-right:1px solid rgba(80,80,80,.28);border-bottom:1px solid rgba(80,80,80,.28);cursor:crosshair}}
.cell.margin{{background:rgba(240,240,240,.14)}}
.baseline-line{{position:absolute;left:0;right:0;height:2px;background:#e00000;z-index:5;pointer-events:none}}
.selection-box{{position:absolute;border:3px solid #1479ff;background:rgba(20,121,255,.08);z-index:4;pointer-events:none;display:none}}
.proposal-list{{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}}.prop{{border:1px solid #aaa;border-radius:6px;padding:3px 6px;font-size:12px;cursor:pointer}}
.accepted{{background:#e8f7eb}}.rejected{{background:#fff3cd}}.manual{{background:#e8f1ff}}.selected{{outline:2px solid #1479ff}}.legend,.imginfo{{font-size:12px;color:#555;margin-top:6px}}
</style>
<h1>SAOL autoannotering → manuell korrigering v4</h1>
<p><b>Boxläge:</b> dra en ram runt en glyph/ett kluster; alla mörka originalpixlar i ramen läggs till i valt förslag. <b>Pixelläge:</b> klicka enskilda pixlar för att lägga till eller ta bort. Rutnät, stödlinje och {margin} px visningsram är kvar.</p>
<div class="toolbar"><button id="export">Exportera korrigerad atlas</button></div>
{''.join(cards)}
<script>
const SCALE={scale},MARGIN={margin};
const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];
const allCards=[];
function colorFor(l){{let h=0;for(const c of l)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length]}}
function rgba(hex,a){{const n=parseInt(hex.slice(1),16),r=(n>>16)&255,g=(n>>8)&255,b=n&255;return `rgba(${{r}},${{g}},${{b}},${{a}})`}}

document.querySelectorAll('.card').forEach(card=>{{
 const W=+card.dataset.w,H=+card.dataset.h,FW=+card.dataset.fw,FH=+card.dataset.fh;
 const INK=JSON.parse(card.dataset.ink),grid=card.querySelector('.grid'),line=card.querySelector('.baseline-line'),selbox=card.querySelector('.selection-box');
 let proposals=JSON.parse(card.dataset.proposals).map((p,i)=>({{...p,id:i,pixels:new Set((p.pixels||[]).map(q=>q[0]+','+q[1]))}}));
 let state={{selected:proposals.length?0:null,baseline:+card.dataset.baseline,mode:'box',drag:false,start:null,current:null}};
 allCards.push([card,proposals,state]);

 function ensureSelected(){{
   if(state.selected!==null)return proposals[state.selected];
   const label=card.querySelector('.label').value.trim()||'?';
   proposals.push({{label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0}});
   state.selected=proposals.length-1;
   return proposals[state.selected];
 }}

 const frag=document.createDocumentFragment();
 for(let fy=0;fy<FH;fy++)for(let fx=0;fx<FW;fx++){{
   const cell=document.createElement('div');cell.className='cell';cell.dataset.fx=fx;cell.dataset.fy=fy;
   const x=fx-MARGIN,y=fy-MARGIN;if(x<0||y<0||x>=W||y>=H)cell.classList.add('margin');
   cell.onpointerdown=e=>{{
     e.preventDefault();
     if(state.mode==='pixel'){{if(x<0||y<0||x>=W||y>=H)return;const p=ensureSelected(),k=x+','+y;if(p.pixels.has(k))p.pixels.delete(k);else p.pixels.add(k);render();return;}}
     state.drag=true;state.start=[fx,fy];state.current=[fx,fy];showSelection();
   }};
   cell.onpointerenter=()=>{{if(state.mode==='box'&&state.drag){{state.current=[fx,fy];showSelection();}}}};
   cell.onpointerup=()=>{{if(state.mode==='box'&&state.drag)commitBox();}};
   frag.appendChild(cell);
 }}
 grid.appendChild(frag);
 document.addEventListener('pointerup',()=>{{if(state.mode==='box'&&state.drag)commitBox();}});

 function showSelection(){{
   if(!state.drag||!state.start||!state.current){{selbox.style.display='none';return;}}
   const x0=Math.min(state.start[0],state.current[0]),y0=Math.min(state.start[1],state.current[1]),x1=Math.max(state.start[0],state.current[0]),y1=Math.max(state.start[1],state.current[1]);
   selbox.style.display='block';selbox.style.left=(x0*SCALE)+'px';selbox.style.top=(y0*SCALE)+'px';selbox.style.width=((x1-x0+1)*SCALE)+'px';selbox.style.height=((y1-y0+1)*SCALE)+'px';
 }}
 function commitBox(){{
   if(!state.drag||!state.start||!state.current)return;
   const p=ensureSelected();
   const fx0=Math.min(state.start[0],state.current[0]),fy0=Math.min(state.start[1],state.current[1]),fx1=Math.max(state.start[0],state.current[0]),fy1=Math.max(state.start[1],state.current[1]);
   for(let fy=fy0;fy<=fy1;fy++)for(let fx=fx0;fx<=fx1;fx++){{const x=fx-MARGIN,y=fy-MARGIN;if(x>=0&&y>=0&&x<W&&y<H&&INK[y][x])p.pixels.add(x+','+y);}}
   state.drag=false;state.start=state.current=null;selbox.style.display='none';render();
 }}
 function renderList(){{
   const box=card.querySelector('.proposal-list');
   box.innerHTML=proposals.map((p,i)=>'<span class="prop '+(p.status==='accepted'?'accepted':p.status==='manual'?'manual':'rejected')+' '+(state.selected===i?'selected':'')+'" data-i="'+i+'">'+p.label+' · '+p.status+' · '+p.pixels.size+' px</span>').join('');
   box.querySelectorAll('.prop').forEach(el=>el.onclick=()=>{{state.selected=+el.dataset.i;card.querySelector('.label').value=proposals[state.selected].label;render();}});
 }}
 function render(){{
   const cells=grid.children;
   for(let i=0;i<cells.length;i++)cells[i].style.backgroundColor='';
   for(let pi=0;pi<proposals.length;pi++){{const p=proposals[pi],alpha=(pi===state.selected?.48:(p.status==='accepted'?.36:.22));for(const k of p.pixels){{const [x,y]=k.split(',').map(Number),fx=x+MARGIN,fy=y+MARGIN;if(fx>=0&&fy>=0&&fx<FW&&fy<FH)cells[fy*FW+fx].style.backgroundColor=rgba(colorFor(p.label),alpha);}}}}
   line.style.top=((state.baseline+MARGIN+1)*SCALE-1)+'px';
   renderList();
 }}
 card.querySelector('.boxmode').onclick=()=>{{state.mode='box';card.querySelector('.boxmode').classList.add('active');card.querySelector('.pixelmode').classList.remove('active')}};
 card.querySelector('.pixelmode').onclick=()=>{{state.mode='pixel';card.querySelector('.pixelmode').classList.add('active');card.querySelector('.boxmode').classList.remove('active')}};
 card.querySelector('.label').onchange=e=>{{if(state.selected===null)return;proposals[state.selected].label=e.target.value.trim();render()}};
 const b=card.querySelector('.baseline');b.onchange=()=>{{state.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=state.baseline;render()}};
 card.querySelector('.up').onclick=()=>{{b.value=Math.max(0,state.baseline-1);b.onchange()}};
 card.querySelector('.down').onclick=()=>{{b.value=Math.min(H-1,state.baseline+1);b.onchange()}};
 card.querySelector('.delete').onclick=()=>{{if(state.selected===null)return;proposals.splice(state.selected,1);state.selected=proposals.length?Math.min(state.selected,proposals.length-1):null;render()}};
 card.querySelector('.new').onclick=()=>{{const label=card.querySelector('.label').value.trim()||'?';proposals.push({{label,status:'manual',pixels:new Set(),contacts:[],external_contacts:0,missing:0,extra:0}});state.selected=proposals.length-1;render()}};
 card.querySelector('.clear').onclick=()=>{{if(confirm('Rensa alla förslag för detta ord?')){{proposals.length=0;state.selected=null;render()}}}};
 const img=card.querySelector('.src');img.onload=()=>card.querySelector('.imginfo').textContent='bild '+img.naturalWidth+'×'+img.naturalHeight;img.onerror=()=>card.querySelector('.imginfo').textContent='BILDFEL';
 if(state.selected!==null)card.querySelector('.label').value=proposals[state.selected].label;
 render();
}});

document.querySelector('#export').onclick=()=>{{
 let words=[];
 for(const [card,proposals,state] of allCards){{
   let anns=[];
   for(const p of proposals){{if(!p.label||!p.pixels.size)continue;let pixels=[...p.pixels].map(k=>k.split(',').map(Number)).sort((a,b)=>a[1]-b[1]||a[0]-b[0]);anns.push({{label:p.label,pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-state.baseline]),candidate_status:p.status}})}}
   if(anns.length)words.push({{source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile,width:+card.dataset.w,height:+card.dataset.h,baseline_y:state.baseline,annotations:anns}})
 }}
 const out={{format:'saol-manual-pixel-atlas-corrected-v4',coordinate_system:'original word crop origin top-left; y_rel = y - baseline_y',words}};
 const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-pixel-atlas-corrected-v4.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)
}};
</script>'''

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"cards={len(cards)} scale={scale} margin={margin} threshold={args.ink_threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
