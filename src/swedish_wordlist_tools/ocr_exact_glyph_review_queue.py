from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from .ocr_glyph_matcher import (
    choose_baseline,
    exact_matches,
    exact_sequence_cover,
    load_facit,
    load_word_debug,
    select_non_overlapping_exact,
)


def _expand_inputs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.glob("saol14-word-debug-*.json")))
        elif p.is_file():
            out.append(p)
    return list(dict.fromkeys(out))


def _analyse_one(path: Path, models) -> dict[str, Any]:
    ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    cover = exact_sequence_cover(ink, width, height, models, expected) if expected else None

    all_exact = exact_matches(ink, width, height, models)
    seed_for_baseline = select_non_overlapping_exact(all_exact)
    baseline = choose_baseline(seed_for_baseline)
    if baseline is None:
        exact_on_baseline = []
    else:
        exact_on_baseline = select_non_overlapping_exact(
            exact_matches(ink, width, height, models, baseline_only=baseline)
        )

    shown = cover if cover is not None else exact_on_baseline
    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    unexplained = sorted([[x, y] for x, y in ink - covered])
    return {
        "path": str(path),
        "expected": expected,
        "headword": debug.get("headword"),
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": debug.get("style") or debug.get("card_dataset", {}).get("style") or "bold",
        "width": width,
        "height": height,
        "ink": sorted([[x, y] for x, y in ink]),
        "baseline": cover[0].baseline if cover else baseline,
        "fully_exact": cover is not None,
        "exact": [
            {
                "label": m.label,
                "style": m.style,
                "x": m.x,
                "baseline": m.baseline,
                "pixels": sorted([list(p) for p in m.pixels]),
            }
            for m in shown
        ],
        "unexplained": unexplained,
        "source": {
            "expected_word": debug.get("expected_word"),
            "page": debug.get("page"),
            "subnr": debug.get("subnr"),
            "source_id": (debug.get("card_dataset") or {}).get("sourceId") or debug.get("source_id") or "",
            "word_file": (debug.get("card_dataset") or {}).get("wordFile") or debug.get("word_file") or "",
        },
    }


def build_html(paths: list[Path], facit_path: Path) -> str:
    models = load_facit(facit_path)
    facit = json.loads(facit_path.read_text(encoding="utf-8"))
    rows = [_analyse_one(p, models) for p in _expand_inputs(paths)]
    payload = json.dumps({"rows": rows, "facit": facit}, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL exakt glyphgranskning</title>
<style>
body{{font-family:system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#111}}
.top{{position:sticky;top:0;z-index:5;background:white;border:1px solid #bbb;padding:10px;margin-bottom:14px}}
.card{{background:white;border:1px solid #bbb;padding:12px;margin:12px 0}}
.card.done{{display:none}}
canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:8px 0;cursor:crosshair}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
input,select,button{{font:inherit;padding:5px}}
.meta{{color:#555;font-size:.92em}} .ok{{color:#075}} .warn{{color:#a40}} .added{{background:#efe}}
.baseline-note{{font-size:.9em;color:#a40}}
</style>
<div class='top'>
 <b>SAOL – exakta glyphar</b>
 <span id='stats'></span>
 <label><input type='checkbox' id='showDone'> Visa även helt exakt tolkade ord</label>
 <button id='save'>Spara uppdaterat facit</button>
 <div><small>Endast 100 % exakta facitmodeller markeras. Om en glyph inte matchar perfekt lämnas dess pixlar svarta och omarkerade. Stödlinjen gäller hela ordet och kan dras vertikalt med musen.</small></div>
</div>
<div id='cards'></div>
<script>
const DATA={payload};
const SCALE=14,M=2; let additions=[];
const cards=document.getElementById('cards');
function keyOf(g){{return JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline]);}}
const known=new Set(DATA.facit.glyphs.map(keyOf));
function renderCard(row){{
 const d=document.createElement('div');d.className='card'+(row.fully_exact?' done':'');d.dataset.done=row.fully_exact?'1':'0';
 const title=document.createElement('div');title.innerHTML='<b>'+escapeHtml(row.expected)+'</b> <span class="meta">sida '+(row.page??'')+' · '+(row.fully_exact?'<span class="ok">helt exakt</span>':'<span class="warn">ofullständig</span>')+'</span>';d.appendChild(title);
 let manualBaseline=!Number.isInteger(row.baseline);
 let currentBaseline=Number.isInteger(row.baseline)?row.baseline:Math.max(0,row.height-2);
 const info=document.createElement('div');info.className='meta';d.appendChild(info);
 const note=document.createElement('div');note.className='baseline-note';d.appendChild(note);
 const c=document.createElement('canvas'),ctx=c.getContext('2d');c.width=(row.width+2*M)*SCALE;c.height=(row.height+2*M)*SCALE;d.appendChild(c);
 let drag=null,sel=null,dragBaseline=false;
 const exactPixels=new Set();
 for(const m of row.exact)for(const [x,y] of m.pixels)exactPixels.add(x+','+y);
 function updateInfo(){{
   info.textContent='Baseline: '+currentBaseline+(manualBaseline?' (manuell)':'')+' · perfekta glyphar: '+row.exact.map(m=>m.label+'@'+m.x).join('  ');
   note.textContent=manualBaseline?'Dra den röda stödlinjen vertikalt till rätt läge innan du märker nya glyphar.':'Dra stödlinjen om du behöver korrigera den.';
 }}
 function baselineCanvasY(){{return (currentBaseline+1+M)*SCALE;}}
 function draw(){{
   ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);
   ctx.strokeStyle='#e4e4e4';ctx.lineWidth=1;
   for(let x=0;x<=row.width+2*M;x++){{const xx=x*SCALE+.5;ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,c.height);ctx.stroke();}}
   for(let y=0;y<=row.height+2*M;y++){{const yy=y*SCALE+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(c.width,yy);ctx.stroke();}}
   for(const [x,y] of row.ink){{
     ctx.fillStyle=exactPixels.has(x+','+y)?'#8f83d8':'#111';
     ctx.fillRect((x+M)*SCALE,(y+M)*SCALE,SCALE,SCALE);
   }}
   const yy=baselineCanvasY();
   ctx.strokeStyle='#d33';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(c.width,yy);ctx.stroke();
   if(sel){{ctx.strokeStyle='#080';ctx.lineWidth=3;const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);ctx.strokeRect((x0+M)*SCALE,(y0+M)*SCALE,(x1-x0+1)*SCALE,(y1-y0+1)*SCALE);}}
 }}
 function pt(e){{const r=c.getBoundingClientRect();return{{x:Math.max(0,Math.min(row.width-1,Math.floor((e.clientX-r.left)/SCALE)-M)),y:Math.max(0,Math.min(row.height-1,Math.floor((e.clientY-r.top)/SCALE)-M)),cy:e.clientY-r.top}};}}
 c.onmousedown=e=>{{
   const p=pt(e);
   if(Math.abs(p.cy-baselineCanvasY())<=Math.max(6,SCALE/2)){{dragBaseline=true;drag=null;sel=null;draw();return;}}
   drag=sel={{x0:p.x,y0:p.y,x1:p.x,y1:p.y}};draw();
 }};
 c.onmousemove=e=>{{
   const p=pt(e);
   if(dragBaseline){{
     currentBaseline=Math.max(0,Math.min(row.height-1,Math.round(p.cy/SCALE-M-1)));
     manualBaseline=true;updateInfo();draw();return;
   }}
   if(!drag)return;drag.x1=p.x;drag.y1=p.y;draw();
 }};
 window.addEventListener('mouseup',()=>{{drag=null;dragBaseline=false;}});
 const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input class="label" size="6"></label><label>Stil <select class="style"><option>bold</option><option>roman</option><option>italic</option></select></label><button class="add">Lägg till markerad variant</button><span class="msg"></span>';d.appendChild(ctrl);
 const style=ctrl.querySelector('.style');style.value=['bold','italic','roman'].includes(row.style)?row.style:'bold';
 ctrl.querySelector('.add').onclick=()=>{{
   const label=ctrl.querySelector('.label').value.trim();
   if(!sel||!label){{ctrl.querySelector('.msg').textContent='Markera raster och skriv etikett.';return;}}
   const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);
   const pts=row.ink.filter(([x,y])=>x>=x0&&x<=x1&&y>=y0&&y<=y1);
   if(!pts.length)return;
   const minx=Math.min(...pts.map(p=>p[0]));
   const rel=pts.map(([x,y])=>[x-minx,y-currentBaseline]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
   const g={{label,style:style.value,pixels_relative_to_baseline:rel,sources:[row.source]}};
   const k=keyOf(g);
   if(known.has(k)||additions.some(a=>keyOf(a)===k)){{ctrl.querySelector('.msg').textContent='Den varianten finns redan.';return;}}
   additions.push(g);ctrl.querySelector('.msg').textContent='Tillagd: '+label+' '+style.value+' ('+rel.length+' pixlar, baseline '+currentBaseline+').';d.classList.add('added');stats();
 }};
 updateInfo();draw();return d;
}}
function escapeHtml(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
DATA.rows.forEach(r=>cards.appendChild(renderCard(r)));
function stats(){{const total=DATA.rows.length,done=DATA.rows.filter(r=>r.fully_exact).length;document.getElementById('stats').textContent=' · '+done+'/'+total+' helt exakta · '+(total-done)+' att granska · '+additions.length+' nya varianter';}}
document.getElementById('showDone').onchange=e=>document.querySelectorAll('.card.done').forEach(c=>c.style.display=e.target.checked?'block':'none');
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-expanded.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
stats();
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Review SAOL debug rasters using only perfect exact glyph matches.")
    ap.add_argument("inputs", nargs="+", type=Path, help="word-debug JSON files or directories containing saol14-word-debug-*.json")
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    files = _expand_inputs(args.inputs)
    if not files:
        raise SystemExit("no word-debug JSON files found")
    args.out.write_text(build_html(files, args.facit), encoding="utf-8")
    print(f"debug_files={len(files)}")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
