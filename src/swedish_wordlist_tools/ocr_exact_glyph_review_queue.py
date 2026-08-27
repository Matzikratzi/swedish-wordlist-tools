from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from .ocr_glyph_matcher import exact_matches, exact_sequence_cover, load_facit, load_word_debug, select_non_overlapping_exact


def _expand_inputs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.glob("saol14-word-debug-*.json")))
        elif p.is_file():
            out.append(p)
    # Stable de-duplication.
    return list(dict.fromkeys(out))


def _analyse_one(path: Path, models) -> dict[str, Any]:
    ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    cover = exact_sequence_cover(ink, width, height, models, expected) if expected else None
    seeds = select_non_overlapping_exact(exact_matches(ink, width, height, models))
    covered = set().union(*(m.pixels for m in (cover or seeds))) if (cover or seeds) else set()
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
        "fully_exact": cover is not None,
        "cover": [
            {"label": m.label, "style": m.style, "x": m.x, "baseline": m.baseline, "pixels": sorted([list(p) for p in m.pixels])}
            for m in (cover or [])
        ],
        "seed": [
            {"label": m.label, "style": m.style, "x": m.x, "baseline": m.baseline, "pixels": sorted([list(p) for p in m.pixels])}
            for m in seeds
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
    incomplete = [r for r in rows if not r["fully_exact"]]
    payload = json.dumps({"rows": rows, "facit": facit}, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL exakt glyphkö</title>
<style>
body{{font-family:system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#111}}
.top{{position:sticky;top:0;z-index:5;background:white;border:1px solid #bbb;padding:10px;margin-bottom:14px}}
.card{{background:white;border:1px solid #bbb;padding:12px;margin:12px 0}}
.card.done{{display:none}} canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:8px 0}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}} input,select,button{{font:inherit;padding:5px}}
.meta{{color:#555;font-size:.92em}} .ok{{color:#075}} .warn{{color:#a40}} .added{{background:#efe}}
</style>
<div class='top'>
 <b>SAOL – exakt glyphgranskning</b>
 <span id='stats'></span>
 <label><input type='checkbox' id='showDone'> Visa även helt exakt tolkade ord</label>
 <button id='save'>Spara uppdaterat facit</button>
 <div><small>Endast perfekta rastermodeller används. Varje glyph får ha egen baseline. Markera en sak som saknas och lägg till en ny exakt variant; etiketten får vara t.ex. <code>g</code>, <code>tt</code> eller flera tecken.</small></div>
</div>
<div id='cards'></div>
<script>
const DATA={payload};
const SCALE=14,M=2; let additions=[];
const cards=document.getElementById('cards');
function keyOf(g){{return JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline]);}}
const known=new Set(DATA.facit.glyphs.map(keyOf));
function nearestBaseline(row, sel){{
 const cx=(Math.min(sel.x0,sel.x1)+Math.max(sel.x0,sel.x1))/2;
 const candidates=(row.cover.length?row.cover:row.seed);
 if(!candidates.length)return null;
 let best=candidates[0],bd=1e9;
 for(const m of candidates){{const d=Math.abs(m.x-cx);if(d<bd){{bd=d;best=m;}}}}
 return best.baseline;
}}
function renderCard(row,idx){{
 const d=document.createElement('div');d.className='card'+(row.fully_exact?' done':'');d.dataset.done=row.fully_exact?'1':'0';
 const title=document.createElement('div');title.innerHTML='<b>'+escapeHtml(row.expected)+'</b> <span class="meta">sida '+(row.page??'')+' · '+(row.fully_exact?'<span class="ok">helt exakt</span>':'<span class="warn">ofullständig</span>')+'</span>';d.appendChild(title);
 const info=document.createElement('div');info.className='meta';info.textContent='Exakta: '+(row.cover.length?row.cover:row.seed).map(m=>m.label+'@'+m.x+'/b'+m.baseline).join('  ');d.appendChild(info);
 const c=document.createElement('canvas'),ctx=c.getContext('2d');c.width=(row.width+2*M)*SCALE;c.height=(row.height+2*M)*SCALE;d.appendChild(c);
 let drag=null,sel=null;
 function draw(){{ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);for(const [x,y] of row.ink){{ctx.fillStyle='#111';ctx.fillRect((x+M)*SCALE,(y+M)*SCALE,SCALE,SCALE);}}for(const m of (row.cover.length?row.cover:row.seed)){{ctx.strokeStyle='#6a5acd';ctx.lineWidth=2;const xs=m.pixels.map(p=>p[0]),ys=m.pixels.map(p=>p[1]);ctx.strokeRect((Math.min(...xs)+M)*SCALE,(Math.min(...ys)+M)*SCALE,(Math.max(...xs)-Math.min(...xs)+1)*SCALE,(Math.max(...ys)-Math.min(...ys)+1)*SCALE);}}if(sel){{ctx.strokeStyle='#080';ctx.lineWidth=3;const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);ctx.strokeRect((x0+M)*SCALE,(y0+M)*SCALE,(x1-x0+1)*SCALE,(y1-y0+1)*SCALE);const b=nearestBaseline(row,sel);if(Number.isInteger(b)){{ctx.strokeStyle='#d33';ctx.lineWidth=2;const yy=(b+1+M)*SCALE;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(c.width,yy);ctx.stroke();}}}}}}
 function pt(e){{const r=c.getBoundingClientRect();return{{x:Math.max(0,Math.min(row.width-1,Math.floor((e.clientX-r.left)/SCALE)-M)),y:Math.max(0,Math.min(row.height-1,Math.floor((e.clientY-r.top)/SCALE)-M))}};}}
 c.onmousedown=e=>{{const p=pt(e);drag=sel={{x0:p.x,y0:p.y,x1:p.x,y1:p.y}};draw();}};c.onmousemove=e=>{{if(!drag)return;const p=pt(e);drag.x1=p.x;drag.y1=p.y;draw();}};window.addEventListener('mouseup',()=>drag=null);
 const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input class="label" size="6"></label><label>Stil <select class="style"><option>bold</option><option>italic</option><option>roman</option></select></label><label>Baseline <input class="baseline" type="number" style="width:5em"></label><button class="add">Lägg till variant</button><span class="msg"></span>';d.appendChild(ctrl);
 const style=ctrl.querySelector('.style');style.value=['bold','italic','roman'].includes(row.style)?row.style:'bold';
 ctrl.querySelector('.baseline').onfocus=()=>{{if(sel){{const b=nearestBaseline(row,sel);if(Number.isInteger(b))ctrl.querySelector('.baseline').value=b;}}}};
 ctrl.querySelector('.add').onclick=()=>{{const label=ctrl.querySelector('.label').value.trim();if(!sel||!label){{ctrl.querySelector('.msg').textContent='Markera raster och skriv etikett.';return;}}let b=parseInt(ctrl.querySelector('.baseline').value,10);if(!Number.isInteger(b))b=nearestBaseline(row,sel);if(!Number.isInteger(b)){{ctrl.querySelector('.msg').textContent='Ange baseline.';return;}}const x0=Math.min(sel.x0,sel.x1),x1=Math.max(sel.x0,sel.x1),y0=Math.min(sel.y0,sel.y1),y1=Math.max(sel.y0,sel.y1);const pts=row.ink.filter(([x,y])=>x>=x0&&x<=x1&&y>=y0&&y<=y1);if(!pts.length)return;const minx=Math.min(...pts.map(p=>p[0]));const rel=pts.map(([x,y])=>[x-minx,y-b]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);const g={{label,style:style.value,pixels_relative_to_baseline:rel,sources:[row.source]}};const k=keyOf(g);if(known.has(k)||additions.some(a=>keyOf(a)===k)){{ctrl.querySelector('.msg').textContent='Den varianten finns redan.';return;}}additions.push(g);ctrl.querySelector('.msg').textContent='Tillagd: '+label+' '+style.value+' ('+rel.length+' pixlar, baseline '+b+').';d.classList.add('added');}};
 draw();return d;
}}
function escapeHtml(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
DATA.rows.forEach((r,i)=>cards.appendChild(renderCard(r,i)));
function stats(){{const total=DATA.rows.length,done=DATA.rows.filter(r=>r.fully_exact).length;document.getElementById('stats').textContent=' · '+done+'/'+total+' helt exakta · '+(total-done)+' att granska · '+additions.length+' nya varianter';}}
document.getElementById('showDone').onchange=e=>document.querySelectorAll('.card.done').forEach(c=>c.style.display=e.target.checked?'block':'none');
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-expanded.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
stats();
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Review only SAOL word debug rasters that cannot yet be covered exactly by facit glyphs.")
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
