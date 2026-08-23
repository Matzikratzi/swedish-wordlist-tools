from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path

from PIL import Image, ImageOps


def _data_uri_with_margin(path: Path, margin: int) -> tuple[str, int, int]:
    with Image.open(path) as im0:
        im = im0.convert("L")
        framed = ImageOps.expand(im, border=margin, fill=255)
        import io
        buf = io.BytesIO()
        framed.save(buf, format="PNG")
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        return uri, framed.width, framed.height


def main() -> int:
    ap = argparse.ArgumentParser(description="Correct auto-proposed manual pixel atlas candidates.")
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

    for i, word in enumerate(payload.get("results", [])):
        if not isinstance(word, dict):
            continue
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not rel or not path.exists():
            continue
        uri, fw, fh = _data_uri_with_margin(path, margin)
        proposals: list[dict[str, object]] = []
        for label, hits in (word.get("matches") or {}).items():
            for hit in hits:
                proposals.append({
                    "label": label,
                    "status": "accepted",
                    "pixels": hit.get("matched_pixels", []),
                    "contacts": hit.get("external_contact_pixels", []),
                    "external_contacts": hit.get("external_contacts", 0),
                    "missing": hit.get("missing", 0),
                    "extra": hit.get("extra", 0),
                })
        for label, hits in (word.get("rejected_candidates") or {}).items():
            for hit in hits:
                proposals.append({
                    "label": label,
                    "status": "topology-rejected",
                    "pixels": hit.get("matched_pixels", []),
                    "contacts": hit.get("external_contact_pixels", []),
                    "external_contacts": hit.get("external_contacts", 0),
                    "missing": hit.get("missing", 0),
                    "extra": hit.get("extra", 0),
                })
        cards.append(f'''<article class="card" data-source-id="{html.escape(str(word.get('source_id') or ''), quote=True)}" data-style="{html.escape(str(word.get('style') or ''), quote=True)}" data-expected="{html.escape(str(word.get('expected_word') or ''), quote=True)}" data-headword="{html.escape(str(word.get('headword') or ''), quote=True)}" data-page="{html.escape(str(word.get('page') or ''), quote=True)}" data-subnr="{html.escape(str(word.get('subnr') or ''), quote=True)}" data-word-file="{html.escape(rel, quote=True)}" data-w="{int(word.get('width') or 0)}" data-h="{int(word.get('height') or 0)}" data-baseline="{int(word.get('baseline_y') or 0)}" data-img="{html.escape(uri, quote=True)}" data-fw="{fw}" data-fh="{fh}" data-proposals='{html.escape(json.dumps(proposals, ensure_ascii=False), quote=True)}'>
<header><strong>{html.escape(str(word.get('expected_word') or ''))}</strong><span class="badge">{html.escape(str(word.get('style') or ''))}</span><span>sida {html.escape(str(word.get('page') or ''))} · subnr {html.escape(str(word.get('subnr') or ''))}</span></header>
<div class="controls"><label>Etikett <input class="label" size="8"></label><button class="pixelmode active" type="button">Pixelläge</button><label>Baslinje y=<input class="baseline" type="number" value="{int(word.get('baseline_y') or 0)}"></label><button class="up" type="button">−1</button><button class="down" type="button">+1</button><button class="clear" type="button">Rensa ordet</button><span class="imginfo">bild {fw}×{fh}</span></div>
<div class="canvaswrap"><canvas width="{fw*scale}" height="{fh*scale}"></canvas></div><div class="proposal-list"></div><div class="legend"></div>
</article>''')

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL candidate editor</title>
<style>*{{box-sizing:border-box}}body{{font-family:system-ui;margin:20px;background:#f3f3f3;color:#171717}}.toolbar{{position:sticky;top:0;z-index:20;background:#f3f3f3ee;padding:8px 0;display:flex;gap:10px;flex-wrap:wrap}}.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:10px;margin:12px 0}}header,.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px}}input,button{{font:inherit}}.active{{font-weight:800;outline:2px solid #1479ff}}.canvaswrap{{display:inline-block;overflow:auto;max-width:100%;border:1px solid #999;background:#ddd}}canvas{{display:block;image-rendering:pixelated;cursor:crosshair;touch-action:none}}.proposal-list{{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}}.prop{{border:1px solid #aaa;border-radius:6px;padding:3px 6px;font-size:12px;cursor:pointer}}.accepted{{background:#e8f7eb}}.rejected{{background:#fff3cd}}.selected{{outline:2px solid #1479ff}}.legend,.imginfo{{font-size:12px;color:#555;margin-top:6px}}.imgerr{{color:#a33;font-weight:700}}</style>
<h1>SAOL autoannotering → manuell korrigering</h1><p>Auto-förslag är förmarkerade. Gröna = topologiskt accepterade, gula = topologiskt tveksamma. Klicka ett förslag för att välja det, ändra etiketten och klicka pixlar för att lägga till/ta bort. Visningen har {margin} px ram runt den sparade ordcroppen; exportkoordinaterna förblir relativa till originalordet.</p><div class="toolbar"><button id="export">Exportera korrigerad atlas</button></div>{''.join(cards)}
<script>
const SCALE={scale},MARGIN={margin};const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];const cards=[];
function colorFor(l){{let h=0;for(const c of l)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length]}}
document.querySelectorAll('.card').forEach(card=>{{
 const cv=card.querySelector('canvas'),ctx=cv.getContext('2d'),W=+card.dataset.w,H=+card.dataset.h,FW=+card.dataset.fw,FH=+card.dataset.fh;
 const img=new Image(); img.src=card.dataset.img;
 let imageReady=false;
 let proposals=JSON.parse(card.dataset.proposals).map((p,i)=>({{...p,id:i,pixels:new Set((p.pixels||[]).map(q=>q[0]+','+q[1]))}}));let state={{selected:proposals.length?0:null,baseline:+card.dataset.baseline}};cards.push([card,proposals,state]);
 function draw(){{ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,cv.width,cv.height);if(imageReady)ctx.drawImage(img,0,0,FW,FH,0,0,cv.width,cv.height);for(const p of proposals){{ctx.fillStyle=colorFor(p.label)+(p.status==='accepted'?'99':'55');for(const k of p.pixels){{let [x,y]=k.split(',').map(Number);ctx.fillRect((x+MARGIN)*SCALE,(y+MARGIN)*SCALE,SCALE,SCALE)}}}}ctx.strokeStyle='#e00000';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,(state.baseline+MARGIN+1)*SCALE);ctx.lineTo(cv.width,(state.baseline+MARGIN+1)*SCALE);ctx.stroke();renderList()}}
 function renderList(){{let box=card.querySelector('.proposal-list');box.innerHTML=proposals.map((p,i)=>'<span class="prop '+(p.status==='accepted'?'accepted':'rejected')+' '+(state.selected===i?'selected':'')+'" data-i="'+i+'">'+p.label+' · '+p.status+' · '+p.pixels.size+' px</span>').join('');box.querySelectorAll('.prop').forEach(el=>el.onclick=()=>{{state.selected=+el.dataset.i;card.querySelector('.label').value=proposals[state.selected].label;draw()}})}}
 function pos(e){{let r=cv.getBoundingClientRect(),x=Math.floor((e.clientX-r.left)/SCALE)-MARGIN,y=Math.floor((e.clientY-r.top)/SCALE)-MARGIN;return [x,y]}}
 cv.onclick=e=>{{if(state.selected===null)return;let [x,y]=pos(e);if(x<0||y<0||x>=W||y>=H)return;let p=proposals[state.selected],k=x+','+y;if(p.pixels.has(k))p.pixels.delete(k);else p.pixels.add(k);draw()}};
 card.querySelector('.label').onchange=e=>{{if(state.selected===null)return;proposals[state.selected].label=e.target.value.trim();draw()}};let b=card.querySelector('.baseline');b.onchange=()=>{{state.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=state.baseline;draw()}};card.querySelector('.up').onclick=()=>{{b.value=Math.max(0,state.baseline-1);b.onchange()}};card.querySelector('.down').onclick=()=>{{b.value=Math.min(H-1,state.baseline+1);b.onchange()}};card.querySelector('.clear').onclick=()=>{{if(confirm('Rensa alla förslag för detta ord?')){{proposals=[];state.selected=null;draw()}}}};
 img.onload=()=>{{imageReady=true;card.querySelector('.imginfo').textContent='bild '+img.naturalWidth+'×'+img.naturalHeight;draw()}};
 img.onerror=()=>{{card.querySelector('.imginfo').innerHTML='<span class="imgerr">bilden kunde inte dekodas</span>';draw()}};
 draw();
}});
document.querySelector('#export').onclick=()=>{{let words=[];for(const [card,proposals,state] of cards){{let anns=[];for(const p of proposals){{if(!p.label||!p.pixels.size)continue;let pixels=[...p.pixels].map(k=>k.split(',').map(Number)).sort((a,b)=>a[1]-b[1]||a[0]-b[0]);anns.push({{label:p.label,pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-state.baseline]),candidate_status:p.status}})}}if(!anns.length)continue;words.push({{source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile,width:+card.dataset.w,height:+card.dataset.h,baseline_y:state.baseline,annotations:anns}})}}let out={{format:'saol-manual-pixel-atlas-corrected-v1',coordinate_system:'original word crop origin top-left; y_rel = y - baseline_y',words}};let blob=new Blob([JSON.stringify(out,null,2)+'\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-pixel-atlas-corrected.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"cards={len(cards)} scale={scale} margin={margin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
