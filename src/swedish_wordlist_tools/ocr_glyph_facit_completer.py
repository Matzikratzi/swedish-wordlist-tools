from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from .ocr_glyph_matcher import analyse, load_facit, load_word_debug


def _payload(debug_path: Path, facit_path: Path) -> dict:
    ink, width, height, debug = load_word_debug(debug_path)
    models = load_facit(facit_path)
    result = analyse(ink, width, height, models)
    facit = json.loads(facit_path.read_text(encoding="utf-8"))
    return {
        "debug": debug,
        "ink": sorted([[x, y] for x, y in ink]),
        "width": width,
        "height": height,
        "analysis": result,
        "facit": facit,
    }


def build_html(debug_path: Path, facit_path: Path) -> str:
    p = _payload(debug_path, facit_path)
    data = json.dumps(p, ensure_ascii=False)
    title = html.escape(str(p["debug"].get("expected_word") or p["debug"].get("headword") or "glyph"))
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL glyph facit completer – {title}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f5f5f5;color:#111}}
.toolbar{{position:sticky;top:0;background:#fff;padding:12px;border:1px solid #ccc;z-index:3}}
canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:16px 0}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
input,select,button{{font:inherit;padding:6px}}
small{{color:#555}} .known{{margin:8px 0}}
</style>
<div class='toolbar'>
  <b>SAOL minimal facitkomplettering</b> — ord: <b>{title}</b>
  <div class='known' id='known'></div>
  <div class='controls'>
    <label>Etikett <input id='label' size='5'></label>
    <label>Stil <select id='style'><option>bold</option><option>italic</option><option>roman</option></select></label>
    <button id='add'>Lägg markerad glyph i facit</button>
    <button id='clear'>Rensa markering</button>
    <button id='save'>Spara uppdaterat facit</button>
  </div>
  <small>Dra en box runt en oidentifierad glyph. Alla svarta källpixlar i boxen används. Sparad y-koordinat blir relativ till den baseline som minimalmatchern har valt.</small>
</div>
<canvas id='c'></canvas>
<div id='msg'></div>
<script>
const DATA={data};
const scale=18, margin=2, W=DATA.width, H=DATA.height, baseline=DATA.analysis.baseline;
const ink=new Set(DATA.ink.map(([x,y])=>x+','+y));
const c=document.getElementById('c'),ctx=c.getContext('2d');
c.width=(W+2*margin)*scale;c.height=(H+2*margin)*scale;
let drag=null,sel=null,added=[];
const exact=DATA.analysis.selected_exact||[];
function draw(){{
 ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);
 for(const k of ink){{const [x,y]=k.split(',').map(Number);ctx.fillStyle='#111';ctx.fillRect((x+margin)*scale,(y+margin)*scale,scale,scale);}}
 for(const m of exact){{ctx.strokeStyle='#6a5acd';ctx.lineWidth=3;const pts=[];for(const [x,y] of DATA.ink){{if(x>=m.x){{/* visual label handled below */}}}}
 }}
 if(Number.isInteger(baseline)){{ctx.strokeStyle='#d33';ctx.lineWidth=2;const yy=(baseline+1+margin)*scale;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(c.width,yy);ctx.stroke();}}
 if(sel){{ctx.strokeStyle='#0a0';ctx.lineWidth=3;const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);ctx.strokeRect((x0+margin)*scale,(y0+margin)*scale,(x1-x0+1)*scale,(y1-y0+1)*scale);}}
}}
function pt(ev){{const r=c.getBoundingClientRect();return {{x:Math.max(0,Math.min(W-1,Math.floor((ev.clientX-r.left)/scale)-margin)),y:Math.max(0,Math.min(H-1,Math.floor((ev.clientY-r.top)/scale)-margin))}};}}
c.onmousedown=e=>{{const p=pt(e);drag={{x0:p.x,y0:p.y,x1:p.x,y1:p.y}};sel=drag;draw();}};
c.onmousemove=e=>{{if(!drag)return;const p=pt(e);drag.x1=p.x;drag.y1=p.y;sel=drag;draw();}};
window.onmouseup=()=>{{drag=null;}};
function selectedPixels(){{if(!sel)return[];const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);return DATA.ink.filter(([x,y])=>x>=x0&&x<=x1&&y>=y0&&y<=y1);}}
function knownText(){{return 'Baseline: '+baseline+' · Exakta glyphar: '+exact.map(m=>m.label+'@x'+m.x+' ('+m.style+')').join(' ');}}
document.getElementById('known').textContent=knownText();
document.getElementById('clear').onclick=()=>{{sel=null;draw();}};
document.getElementById('add').onclick=()=>{{
 const label=document.getElementById('label').value.trim();const style=document.getElementById('style').value;const pts=selectedPixels();
 if(!label||!pts.length||!Number.isInteger(baseline)){{document.getElementById('msg').textContent='Behöver etikett, markering och känd baseline.';return;}}
 const minx=Math.min(...pts.map(p=>p[0]));const rel=pts.map(([x,y])=>[x-minx,y-baseline]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 const row={{label,style,pixels_relative_to_baseline:rel,sources:[{{expected_word:DATA.debug.expected_word,page:DATA.debug.page,subnr:DATA.debug.subnr,source_id:DATA.debug.card_dataset?.sourceId||'',word_file:DATA.debug.card_dataset?.wordFile||''}}]}};
 const key=JSON.stringify([label,style,rel]);const exists=DATA.facit.glyphs.some(g=>JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline])===key)||added.some(g=>JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline])===key);
 if(!exists)added.push(row);
 document.getElementById('msg').textContent=exists?'Modellen finns redan.':'Tillagd lokalt: '+label+' '+style+' ('+rel.length+' pixlar).';sel=null;draw();
}};
document.getElementById('save').onclick=()=>{{
 const out=structuredClone(DATA.facit);out.glyphs=[...out.glyphs,...added];out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));
 const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-completed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}};
draw();
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Standalone minimal UI to add missing SAOL glyph models to canonical facit.")
    ap.add_argument("word_debug", type=Path)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text(build_html(args.word_debug, args.facit), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
