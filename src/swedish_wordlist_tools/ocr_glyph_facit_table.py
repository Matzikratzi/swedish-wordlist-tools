from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

FACIT_FORMAT = "saol14-manual-glyph-facit-v1"
STYLE_ORDER = ["bold", "roman", "italic"]
STYLE_LABEL = {"bold": "Fet", "roman": "Roman", "italic": "Kursiv"}


def load_facit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FACIT_FORMAT:
        raise ValueError(f"unsupported facit format: {payload.get('format')!r}")
    return payload


def _sort_key(label: str) -> tuple:
    order = "abcdefghijklmnopqrstuvwxyzåäö"
    if label and label[0].lower() in order:
        return (1, order.index(label[0].lower()), label.lower(), label)
    return (0, label)


def build_html(facit_path: Path) -> str:
    facit = load_facit(facit_path)
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    all_ys: list[int] = []
    for glyph in facit.get("glyphs") or []:
        label = str(glyph.get("label") or "")
        style = str(glyph.get("style") or "roman")
        if not label:
            continue
        groups[label][style].append(glyph)
        all_ys.extend(int(y) for _, y in glyph.get("pixels_relative_to_baseline") or [])

    labels = sorted(groups, key=_sort_key)
    global_min_y = min(all_ys + [-2])
    global_max_y = max(all_ys + [2])
    payload = {
        "labels": labels,
        "groups": groups,
        "global_min_y": global_min_y,
        "global_max_y": global_max_y,
    }
    data = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL glyphfacit – jämförelse</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f6f6f6;color:#111}}
h1{{margin:0 0 8px}} .meta{{color:#555;margin-bottom:18px}}
#header,#rows{{min-width:max-content}}
.header-row,.glyph-row{{display:grid;grid-template-columns:64px var(--bold-w) var(--roman-w) var(--italic-w);column-gap:24px;align-items:start}}
.header-row{{position:sticky;top:0;z-index:5;background:#f6f6f6;padding:8px 0 10px;border-bottom:1px solid #ccc;font-weight:700}}
.glyph-row{{padding:7px 0}}
.label{{font-size:26px;font-weight:700;text-align:center;padding-top:18px}}
.style-zone{{display:flex;gap:12px;align-items:flex-start;min-height:1px}}
.variant{{display:flex;flex-direction:column;align-items:flex-start}}
.cap{{font-size:11px;color:#666;height:16px;white-space:nowrap}}
canvas{{image-rendering:pixelated;display:block;background:white}}
.empty{{color:#bbb;font-size:12px;padding-top:30px}}
</style>
<h1>SAOL glyphfacit</h1>
<div class='meta'>En rad per glyph. Fet, roman och kursiv ligger i lösa stilzoner utan cellramar. Alla modeller delar samma stödlinje och pixelrutnät. Flera varianter ligger bredvid varandra och gör sin stilzon bredare för alla rader.</div>
<div id='header'></div>
<div id='rows'></div>
<script>
const DATA={data};
const SCALE=12, PADX=2, PADY=2, VARIANT_GAP=12;
const GLOBAL_MIN_Y=DATA.global_min_y, GLOBAL_MAX_Y=DATA.global_max_y;
const GLOBAL_H=GLOBAL_MAX_Y-GLOBAL_MIN_Y+1;

function glyphWidth(g){{
 const pts=g.pixels_relative_to_baseline||[];
 if(!pts.length)return 0;
 const xs=pts.map(p=>p[0]);
 return (Math.max(...xs)-Math.min(...xs)+1+2*PADX)*SCALE;
}}
function groupWidth(rows){{
 if(!rows.length)return 0;
 return rows.reduce((s,g)=>s+glyphWidth(g),0)+VARIANT_GAP*(rows.length-1);
}}
const styleWidths={{}};
for(const style of ['bold','roman','italic']){{
 let w=80;
 for(const label of DATA.labels){{
   const rows=(DATA.groups[label]&&DATA.groups[label][style])||[];
   w=Math.max(w,groupWidth(rows));
 }}
 styleWidths[style]=w;
}}
document.documentElement.style.setProperty('--bold-w',styleWidths.bold+'px');
document.documentElement.style.setProperty('--roman-w',styleWidths.roman+'px');
document.documentElement.style.setProperty('--italic-w',styleWidths.italic+'px');

function drawGlyph(canvas,g){{
 const pts=g.pixels_relative_to_baseline||[];
 if(!pts.length)return;
 const xs=pts.map(p=>p[0]);
 const minx=Math.min(...xs), maxx=Math.max(...xs), w=maxx-minx+1;
 canvas.width=(w+2*PADX)*SCALE;
 canvas.height=(GLOBAL_H+2*PADY)*SCALE;
 const ctx=canvas.getContext('2d');
 ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.strokeStyle='#ddd';ctx.lineWidth=1;
 for(let gx=0;gx<=w+2*PADX;gx++){{
   const xx=gx*SCALE+0.5;ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,canvas.height);ctx.stroke();
 }}
 for(let gy=0;gy<=GLOBAL_H+2*PADY;gy++){{
   const yy=gy*SCALE+0.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(canvas.width,yy);ctx.stroke();
 }}
 for(const [x,y] of pts){{
   ctx.fillStyle='#111';ctx.fillRect((x-minx+PADX)*SCALE,(y-GLOBAL_MIN_Y+PADY)*SCALE,SCALE,SCALE);
 }}
 const baselineY=(0-GLOBAL_MIN_Y+PADY+1)*SCALE;
 ctx.strokeStyle='#d33';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,baselineY);ctx.lineTo(canvas.width,baselineY);ctx.stroke();
}}

const header=document.getElementById('header');
const hr=document.createElement('div');hr.className='header-row';
for(const text of ['','Fet','Roman','Kursiv']){{const d=document.createElement('div');d.textContent=text;hr.appendChild(d);}}
header.appendChild(hr);

const root=document.getElementById('rows');
for(const label of DATA.labels){{
 const row=document.createElement('div');row.className='glyph-row';
 const lab=document.createElement('div');lab.className='label';lab.textContent=label;row.appendChild(lab);
 for(const style of ['bold','roman','italic']){{
   const zone=document.createElement('div');zone.className='style-zone';
   const models=(DATA.groups[label]&&DATA.groups[label][style])||[];
   if(!models.length){{const e=document.createElement('div');e.className='empty';e.textContent='–';zone.appendChild(e);}}
   else models.forEach((g,i)=>{{
     const v=document.createElement('div');v.className='variant';
     const cap=document.createElement('div');cap.className='cap';
     cap.textContent=models.length>1?('variant '+(i+1)+'/'+models.length):'';
     const c=document.createElement('canvas');drawGlyph(c,g);
     v.append(cap,c);zone.appendChild(v);
   }});
   row.appendChild(zone);
 }}
 root.appendChild(row);
}}
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render canonical SAOL glyph facit as a fuzzy aligned HTML overview.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text(build_html(args.facit), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
