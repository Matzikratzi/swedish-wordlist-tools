from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

from .ocr_exact_glyph_review_queue import _expand_inputs, _raw_baseline_guess
from .ocr_glyph_facit_table import build_html as build_facit_html
from .ocr_glyph_matcher import exact_matches, exact_sequence_cover, load_facit, load_word_debug

VALID_STYLES = {"bold", "roman", "italic"}
STYLE_SHORT = {"bold": "b", "roman": "r", "italic": "i"}


def _expected_partial(matches, expected: str):
    """Choose pixel-disjoint exact matches in expected-word order.

    Glyph bounding boxes may overlap horizontally.  Ordering therefore follows
    each glyph's left anchor, not the previous glyph's rightmost x.  Actual black
    pixels must remain exclusive.
    """
    if not expected or not matches:
        return []
    rows = sorted(matches, key=lambda m: (m.x, -len(m.label), -m.model_pixels, m.label, m.style))

    @lru_cache(maxsize=None)
    def dfs(i: int, expected_pos: int, min_anchor_x: int, occupied_key: tuple[tuple[int, int], ...]):
        occupied = set(occupied_key)
        if i >= len(rows):
            return (0, 0, ())
        best = dfs(i + 1, expected_pos, min_anchor_x, occupied_key)
        m = rows[i]
        if m.x >= min_anchor_x and m.label and not occupied.intersection(m.pixels):
            p = expected.find(m.label, expected_pos)
            while p >= 0:
                new_occupied = tuple(sorted(occupied | set(m.pixels)))
                tail_chars, tail_pixels, tail_idx = dfs(
                    i + 1,
                    p + len(m.label),
                    m.x + 1,
                    new_occupied,
                )
                cand = (
                    len(m.label) + tail_chars,
                    m.model_pixels + tail_pixels,
                    (i,) + tail_idx,
                )
                if (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
                p = expected.find(m.label, p + 1)
        return best

    _, _, idx = dfs(0, 0, 0, ())
    return [rows[i] for i in idx]


def _analyse_one(path: Path, models):
    ink, width, height, debug = load_word_debug(path)
    expected = str(debug.get("expected_word") or debug.get("headword") or "")
    word_style = str(debug.get("style") or (debug.get("card_dataset") or {}).get("style") or "bold")

    # Match all learned styles freely. Style belongs to each glyph, not to the
    # whole word/card. This also lets mixed-style source rows work naturally.
    cover = exact_sequence_cover(ink, width, height, models, expected) if expected else None
    if cover:
        baseline = cover[0].baseline
        shown = cover
        source = "exact-cover"
    else:
        baseline = _raw_baseline_guess(ink, height)
        source = "raw-density"
        if baseline is None:
            shown = []
        else:
            shown = _expected_partial(
                exact_matches(ink, width, height, models, baseline_only=baseline),
                expected,
            )

    covered = set().union(*(m.pixels for m in shown)) if shown else set()
    return {
        "expected": expected,
        "page": debug.get("page"),
        "subnr": debug.get("subnr"),
        "style": word_style,
        "width": width,
        "height": height,
        "ink": sorted([list(p) for p in ink]),
        "baseline": baseline,
        "baseline_source": source,
        "fully_exact": cover is not None,
        "exact": [
            {"label": m.label, "style": m.style, "x": m.x, "baseline": m.baseline, "pixels": sorted([list(p) for p in m.pixels])}
            for m in shown
        ],
        "unexplained": sorted([list(p) for p in ink - covered]),
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
    data = json.dumps({"rows": rows, "facit": facit}, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL exakt glyphgranskning</title>
<style>
body{{font-family:system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#111}}
.top{{position:sticky;top:0;z-index:5;background:white;border:1px solid #bbb;padding:10px;margin-bottom:14px}}
.card{{background:white;border:1px solid #bbb;padding:12px;margin:12px 0}} .card.done{{display:none}}
canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:8px 0;cursor:crosshair}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}} input,button{{font:inherit;padding:5px}}
.meta{{color:#555;font-size:.92em}} .ok{{color:#075}} .warn{{color:#a40}} .added{{background:#efe}} .note{{color:#765;font-size:.9em}}
code{{background:#eee;padding:1px 4px;border-radius:3px}}
</style>
<div class='top'>
<b>SAOL – exakta glyphar</b> <span id='stats'></span>
<label><input type='checkbox' id='showDone'> Visa även helt exakta ord</label>
<button id='save'>Spara uppdaterat facit</button>
<a href='glyph-facit-table.html' target='_blank'>Glyphfacit</a>
<div><small>Automatiska träffar söker fritt bland alla stilar men måste vara 100 % exakta och ligga i rätt ordningsföljd. Glyphars x-utbredning får överlappa men de får aldrig dela svarta pixlar. Vid manuell märkning skriv stil i etiketten: <code>f{{i}}</code> kursiv, <code>f{{r}}</code> roman, <code>f{{b}}</code> fet. Alt-dra tar bort pixlar; Shift-dra lägger tillbaka dem.</small></div>
</div><div id='cards'></div>
<script>
const DATA={data}; const SCALE=14,M=2; let additions=[];
const cards=document.getElementById('cards');
const keyOf=g=>JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline]);
const known=new Set(DATA.facit.glyphs.map(keyOf));
const pkey=(x,y)=>x+','+y;
const styleShort={{bold:'b',roman:'r',italic:'i'}};

function parseStyledLabel(raw, fallbackStyle){{
 const s=raw.trim();
 const m=s.match(/^(.*)\\{{([bri])\\}}$/i);
 if(!m)return {{label:s,style:fallbackStyle}};
 const style={{b:'bold',r:'roman',i:'italic'}}[m[2].toLowerCase()];
 return {{label:m[1],style}};
}}
function styledLabel(label,style){{return label+'{{'+(styleShort[style]||'?')+'}}';}}

function renderCard(row){{
 const d=document.createElement('div'); d.className='card'+(row.fully_exact?' done':'');
 d.innerHTML='<b>'+esc(row.expected)+'</b> <span class="meta">sida '+(row.page??'')+' · '+(row.fully_exact?'<span class="ok">helt exakt</span>':'<span class="warn">ofullständig</span>')+'</span>';
 let baseline=Number.isInteger(row.baseline)?row.baseline:Math.max(0,row.height-2), manual=false;
 const info=document.createElement('div'); info.className='meta'; d.appendChild(info);
 const note=document.createElement('div'); note.className='note'; note.textContent='Dra den röda stödlinjen vid behov.'; d.appendChild(note);
 const c=document.createElement('canvas'),ctx=c.getContext('2d'); c.width=(row.width+2*M)*SCALE; c.height=(row.height+2*M)*SCALE; d.appendChild(c);
 const inkSet=new Set(row.ink.map(([x,y])=>pkey(x,y)));
 const exactSet=new Set(); for(const m of row.exact)for(const [x,y] of m.pixels)exactSet.add(pkey(x,y));
 let rect=null, dragRect=false, dragBaseline=false, pixelMode=null; const selected=new Set();
 const baseY=()=> (baseline+1+M)*SCALE;
 function updateInfo(){{info.textContent='Baseline: '+baseline+(manual?' (manuell)':' ('+row.baseline_source+')')+' · perfekta glyphar: '+row.exact.map(m=>styledLabel(m.label,m.style)+'@'+m.x).join('  ');}}
 function draw(){{
  ctx.fillStyle='#fff';ctx.fillRect(0,0,c.width,c.height);ctx.strokeStyle='#e4e4e4';ctx.lineWidth=1;
  for(let x=0;x<=row.width+2*M;x++){{let xx=x*SCALE+.5;ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,c.height);ctx.stroke();}}
  for(let y=0;y<=row.height+2*M;y++){{let yy=y*SCALE+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(c.width,yy);ctx.stroke();}}
  for(const [x,y] of row.ink){{ctx.fillStyle=selected.has(pkey(x,y))?'#2a9d4b':(exactSet.has(pkey(x,y))?'#8f83d8':'#111');ctx.fillRect((x+M)*SCALE,(y+M)*SCALE,SCALE,SCALE);}}
  ctx.strokeStyle='#d33';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(0,baseY());ctx.lineTo(c.width,baseY());ctx.stroke();
  if(rect){{const x0=Math.min(rect.x0,rect.x1),x1=Math.max(rect.x0,rect.x1),y0=Math.min(rect.y0,rect.y1),y1=Math.max(rect.y0,rect.y1);ctx.strokeStyle='#080';ctx.lineWidth=2;ctx.strokeRect((x0+M)*SCALE,(y0+M)*SCALE,(x1-x0+1)*SCALE,(y1-y0+1)*SCALE);}}
 }}
 function pt(e){{const r=c.getBoundingClientRect();return{{x:Math.max(0,Math.min(row.width-1,Math.floor((e.clientX-r.left)/SCALE)-M)),y:Math.max(0,Math.min(row.height-1,Math.floor((e.clientY-r.top)/SCALE)-M)),cy:e.clientY-r.top}};}}
 function editPixel(p,mode){{const k=pkey(p.x,p.y);if(!inkSet.has(k))return;if(mode==='add')selected.add(k);else if(mode==='remove')selected.delete(k);}}
 function fillRectSelection(){{selected.clear();if(!rect)return;const x0=Math.min(rect.x0,rect.x1),x1=Math.max(rect.x0,rect.x1),y0=Math.min(rect.y0,rect.y1),y1=Math.max(rect.y0,rect.y1);for(const [x,y] of row.ink)if(x>=x0&&x<=x1&&y>=y0&&y<=y1)selected.add(pkey(x,y));}}
 c.onmousedown=e=>{{const p=pt(e);if(e.altKey||e.shiftKey){{pixelMode=e.altKey?'remove':'add';editPixel(p,pixelMode);draw();return;}}if(Math.abs(p.cy-baseY())<=Math.max(6,SCALE/2)){{dragBaseline=true;rect=null;selected.clear();draw();return;}}dragRect=true;rect={{x0:p.x,y0:p.y,x1:p.x,y1:p.y}};selected.clear();draw();}};
 c.onmousemove=e=>{{const p=pt(e);if(pixelMode){{editPixel(p,pixelMode);draw();return;}}if(dragBaseline){{baseline=Math.max(0,Math.min(row.height-1,Math.round(p.cy/SCALE-M-1)));manual=true;updateInfo();draw();return;}}if(dragRect){{rect.x1=p.x;rect.y1=p.y;draw();}}}};
 c.onmouseup=()=>{{if(dragRect)fillRectSelection();dragRect=false;dragBaseline=false;pixelMode=null;draw();}}; c.onmouseleave=()=>{{if(dragRect)fillRectSelection();dragRect=false;dragBaseline=false;pixelMode=null;draw();}};
 const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input class="label" size="10" placeholder="f{{i}}"></label><button class="add">Lägg till markerad variant</button><button class="clear">Rensa markering</button><span class="msg"></span>';d.appendChild(ctrl);
 const labelInput=ctrl.querySelector('.label');
 ctrl.querySelector('.clear').onclick=()=>{{selected.clear();rect=null;draw();}};
 ctrl.querySelector('.add').onclick=()=>{{
   const parsed=parseStyledLabel(labelInput.value,row.style);
   const label=parsed.label, style=parsed.style;
   if(!label||!selected.size){{ctrl.querySelector('.msg').textContent='Markera pixlar och skriv etikett, t.ex. f{{i}}.';return;}}
   const pts=[...selected].map(k=>k.split(',').map(Number));
   const minx=Math.min(...pts.map(p=>p[0]));
   const rel=pts.map(([x,y])=>[x-minx,y-baseline]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
   const g={{label,style,pixels_relative_to_baseline:rel,sources:[row.source]}};
   const k=keyOf(g);
   if(known.has(k)||additions.some(a=>keyOf(a)===k)){{ctrl.querySelector('.msg').textContent='Den varianten finns redan.';return;}}
   additions.push(g);ctrl.querySelector('.msg').textContent='Tillagd: '+styledLabel(label,style)+' ('+rel.length+' pixlar).';d.classList.add('added');stats();
 }};
 updateInfo();draw();return d;
}}
function esc(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
DATA.rows.forEach(r=>cards.appendChild(renderCard(r)));
function stats(){{const total=DATA.rows.length,done=DATA.rows.filter(r=>r.fully_exact).length;document.getElementById('stats').textContent=' · '+done+'/'+total+' helt exakta · '+(total-done)+' att granska · '+additions.length+' nya varianter';}}
document.getElementById('showDone').onchange=e=>document.querySelectorAll('.card.done').forEach(c=>c.style.display=e.target.checked?'block':'none');
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const stamp=new Date().toISOString().replace(/[-:]/g,'').replace(/\\.\\d{{3}}Z$/,'Z');const name='saol14-manual-glyph-facit-expanded-'+out.glyphs.length+'-'+stamp+'.json';const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
stats();
</script>"""


def main() -> int:
    ap=argparse.ArgumentParser(description="Review exact SAOL glyphs with per-glyph style labels and pixel-refinable manual selection.")
    ap.add_argument("inputs",nargs="+",type=Path)
    ap.add_argument("--facit",type=Path,default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--facit-html",type=Path,default=Path("/tmp/glyph-facit-table.html"))
    args=ap.parse_args(); files=_expand_inputs(args.inputs)
    if not files: raise SystemExit("no word-debug JSON files found")
    args.out.write_text(build_html(files,args.facit),encoding="utf-8")
    args.facit_html.write_text(build_facit_html(args.facit),encoding="utf-8")
    print(f"debug_files={len(files)}")
    print(args.out)
    print(f"facit_html={args.facit_html}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
