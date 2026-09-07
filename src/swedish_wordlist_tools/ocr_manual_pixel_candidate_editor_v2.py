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
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), framed.width, framed.height


def main() -> int:
    ap = argparse.ArgumentParser(description="Correct auto-proposed pixel candidates using a visible IMG layer and transparent canvas overlay.")
    ap.add_argument("matches", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=18)
    ap.add_argument("--margin", type=int, default=2)
    args = ap.parse_args()

    payload = json.loads(args.matches.read_text(encoding="utf-8"))
    scale = max(4, args.scale)
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
        cards.append(f'''<article class="card" data-source-id="{html.escape(str(word.get('source_id') or ''), quote=True)}" data-style="{html.escape(str(word.get('style') or ''), quote=True)}" data-expected="{html.escape(str(word.get('expected_word') or ''), quote=True)}" data-headword="{html.escape(str(word.get('headword') or ''), quote=True)}" data-page="{html.escape(str(word.get('page') or ''), quote=True)}" data-subnr="{html.escape(str(word.get('subnr') or ''), quote=True)}" data-word-file="{html.escape(rel, quote=True)}" data-w="{int(word.get('width') or 0)}" data-h="{int(word.get('height') or 0)}" data-baseline="{int(word.get('baseline_y') or 0)}" data-proposals='{html.escape(json.dumps(proposals, ensure_ascii=False), quote=True)}'>
<header><strong>{html.escape(str(word.get('expected_word') or ''))}</strong><span class="badge">{html.escape(str(word.get('style') or ''))}</span><span>uppslagsord: <b>{html.escape(str(word.get('headword') or '')) or '(saknas)'}</b></span><span>sida {html.escape(str(word.get('page') or ''))} · subnr {html.escape(str(word.get('subnr') or ''))}</span></header>
<div class="controls"><label>Etikett <input class="label" size="8"></label><label>Baslinje y=<input class="baseline" type="number" value="{int(word.get('baseline_y') or 0)}"></label><button class="up" type="button">−1</button><button class="down" type="button">+1</button><button class="delete" type="button">Ta bort valt förslag</button><button class="clear" type="button">Rensa ordet</button><span class="imginfo">bild {fw}×{fh}</span></div>
<div class="stack" style="width:{fw*scale}px;height:{fh*scale}px"><img class="src" src="{uri}" width="{fw*scale}" height="{fh*scale}" alt=""><canvas width="{fw*scale}" height="{fh*scale}"></canvas></div>
<div class="proposal-list"></div><div class="legend"></div>
</article>''')

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL candidate editor v2</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui;margin:20px;background:#f3f3f3;color:#171717}}.toolbar{{position:sticky;top:0;z-index:20;background:#f3f3f3ee;padding:8px 0}}.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:10px;margin:12px 0}}header,.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px}}input,button{{font:inherit}}.stack{{position:relative;display:block;overflow:hidden;border:1px solid #999;background:white}}.stack img,.stack canvas{{position:absolute;left:0;top:0;display:block;image-rendering:pixelated}}.stack canvas{{z-index:2;cursor:crosshair;touch-action:none}}.stack img{{z-index:1}}.proposal-list{{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}}.prop{{border:1px solid #aaa;border-radius:6px;padding:3px 6px;font-size:12px;cursor:pointer}}.accepted{{background:#e8f7eb}}.rejected{{background:#fff3cd}}.selected{{outline:2px solid #1479ff}}.legend,.imginfo{{font-size:12px;color:#555;margin-top:6px}}
</style>
<h1>SAOL autoannotering → manuell korrigering v2</h1>
<p>Originalordet visas nu som ett vanligt bildlager. Canvasen ovanpå innehåller bara markeringar och baslinje. Klicka ett förslag för att välja det; klicka sedan pixlar för att lägga till/ta bort. Visningsram: {margin} px.</p>
<div class="toolbar"><button id="export">Exportera korrigerad atlas</button></div>
{''.join(cards)}
<script>
const SCALE={scale},MARGIN={margin};
const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];
const allCards=[];
function colorFor(l){{let h=0;for(const c of l)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length]}}
document.querySelectorAll('.card').forEach(card=>{{
 const cv=card.querySelector('canvas'),ctx=cv.getContext('2d'),W=+card.dataset.w,H=+card.dataset.h;
 let proposals=JSON.parse(card.dataset.proposals).map((p,i)=>({{...p,id:i,pixels:new Set((p.pixels||[]).map(q=>q[0]+','+q[1]))}}));
 let state={{selected:proposals.length?0:null,baseline:+card.dataset.baseline}};
 allCards.push([card,proposals,state]);
 function renderList(){{
   const box=card.querySelector('.proposal-list');
   box.innerHTML=proposals.map((p,i)=>'<span class="prop '+(p.status==='accepted'?'accepted':'rejected')+' '+(state.selected===i?'selected':'')+'" data-i="'+i+'">'+p.label+' · '+p.status+' · '+p.pixels.size+' px</span>').join('');
   box.querySelectorAll('.prop').forEach(el=>el.onclick=()=>{{state.selected=+el.dataset.i;card.querySelector('.label').value=proposals[state.selected].label;draw()}});
 }}
 function draw(){{
   ctx.clearRect(0,0,cv.width,cv.height);
   for(const p of proposals){{ctx.fillStyle=colorFor(p.label)+(p.status==='accepted'?'99':'55');for(const k of p.pixels){{const [x,y]=k.split(',').map(Number);ctx.fillRect((x+MARGIN)*SCALE,(y+MARGIN)*SCALE,SCALE,SCALE)}}}}
   ctx.strokeStyle='#e00000';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,(state.baseline+MARGIN+1)*SCALE);ctx.lineTo(cv.width,(state.baseline+MARGIN+1)*SCALE);ctx.stroke();renderList();
 }}
 function pos(e){{const r=cv.getBoundingClientRect();return [Math.floor((e.clientX-r.left)/SCALE)-MARGIN,Math.floor((e.clientY-r.top)/SCALE)-MARGIN]}}
 cv.onclick=e=>{{if(state.selected===null)return;const [x,y]=pos(e);if(x<0||y<0||x>=W||y>=H)return;const p=proposals[state.selected],k=x+','+y;if(p.pixels.has(k))p.pixels.delete(k);else p.pixels.add(k);draw()}};
 card.querySelector('.label').onchange=e=>{{if(state.selected===null)return;proposals[state.selected].label=e.target.value.trim();draw()}};
 const b=card.querySelector('.baseline');b.onchange=()=>{{state.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=state.baseline;draw()}};
 card.querySelector('.up').onclick=()=>{{b.value=Math.max(0,state.baseline-1);b.onchange()}};card.querySelector('.down').onclick=()=>{{b.value=Math.min(H-1,state.baseline+1);b.onchange()}};
 card.querySelector('.delete').onclick=()=>{{if(state.selected===null)return;proposals.splice(state.selected,1);state.selected=proposals.length?Math.min(state.selected,proposals.length-1):null;draw()}};
 card.querySelector('.clear').onclick=()=>{{if(confirm('Rensa alla förslag för detta ord?')){{proposals.length=0;state.selected=null;draw()}}}};
 const img=card.querySelector('.src');img.onload=()=>card.querySelector('.imginfo').textContent='bild '+img.naturalWidth+'×'+img.naturalHeight;img.onerror=()=>card.querySelector('.imginfo').textContent='BILDFEL';
 draw();
}});
document.querySelector('#export').onclick=()=>{{let words=[];for(const [card,proposals,state] of allCards){{let anns=[];for(const p of proposals){{if(!p.label||!p.pixels.size)continue;let pixels=[...p.pixels].map(k=>k.split(',').map(Number)).sort((a,b)=>a[1]-b[1]||a[0]-b[0]);anns.push({{label:p.label,pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-state.baseline]),candidate_status:p.status}})}}if(anns.length)words.push({{source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile,width:+card.dataset.w,height:+card.dataset.h,baseline_y:state.baseline,annotations:anns}})}}const out={{format:'saol-manual-pixel-atlas-corrected-v2',coordinate_system:'original word crop origin top-left; y_rel = y - baseline_y',words}};const blob=new Blob([JSON.stringify(out,null,2)+'\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-pixel-atlas-corrected-v2.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"cards={len(cards)} scale={scale} margin={margin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
