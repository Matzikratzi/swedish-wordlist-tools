from __future__ import annotations

import argparse
import html
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
    # Swedish-ish ordering for the labels we expect, with symbols first.
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
<title>SAOL glyphfacit – tabell</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f6f6f6;color:#111}}
h1{{margin:0 0 8px}} .meta{{color:#555;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;background:white}}
th,td{{border:1px solid #ccc;vertical-align:top;padding:8px}}
th{{position:sticky;top:0;background:#eee;z-index:2}}
th:first-child,td:first-child{{width:70px;text-align:center;font-size:28px;font-weight:700;background:#fafafa}}
.variants{{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}}
.variant{{border:1px solid #bbb;border-radius:6px;padding:6px;background:#fff}}
.variant .cap{{font-size:12px;color:#555;margin-bottom:4px}}
canvas{{image-rendering:pixelated;display:block;background:white}}
.empty{{color:#aaa;font-style:italic}}
</style>
<h1>SAOL glyphfacit</h1>
<div class='meta'>En rad per etikett. Kolumner: fet, roman, kursiv. Alla modeller delar samma vertikala koordinatsystem och samma stödlinje. Rutnätet visar originalets rasterpixlar.</div>
<table id='t'>
<thead><tr><th>Glyph</th><th>Fet</th><th>Roman</th><th>Kursiv</th></tr></thead>
<tbody></tbody>
</table>
<script>
const DATA={data};
const SCALE=12, PADX=2, PADY=2;
const GLOBAL_MIN_Y=DATA.global_min_y, GLOBAL_MAX_Y=DATA.global_max_y;
const GLOBAL_H=GLOBAL_MAX_Y-GLOBAL_MIN_Y+1;

function drawGlyph(canvas,g){{
 const pts=g.pixels_relative_to_baseline||[];
 if(!pts.length)return;
 const xs=pts.map(p=>p[0]);
 const minx=Math.min(...xs), maxx=Math.max(...xs);
 const w=maxx-minx+1;
 canvas.width=(w+2*PADX)*SCALE;
 canvas.height=(GLOBAL_H+2*PADY)*SCALE;
 const ctx=canvas.getContext('2d');
 ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);

 // Pixel grid: identical y rows in every canvas.
 ctx.strokeStyle='#ddd';ctx.lineWidth=1;
 for(let gx=0;gx<=w+2*PADX;gx++){{
   const xx=gx*SCALE+0.5;
   ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,canvas.height);ctx.stroke();
 }}
 for(let gy=0;gy<=GLOBAL_H+2*PADY;gy++){{
   const yy=gy*SCALE+0.5;
   ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(canvas.width,yy);ctx.stroke();
 }}

 // Source ink.
 for(const [x,y] of pts){{
   ctx.fillStyle='#111';
   ctx.fillRect((x-minx+PADX)*SCALE,(y-GLOBAL_MIN_Y+PADY)*SCALE,SCALE,SCALE);
 }}

 // Support line directly underneath raster row y=0.
 const baselineY=(0-GLOBAL_MIN_Y+PADY+1)*SCALE;
 ctx.strokeStyle='#d33';ctx.lineWidth=2;
 ctx.beginPath();ctx.moveTo(0,baselineY);ctx.lineTo(canvas.width,baselineY);ctx.stroke();
}}

const tb=document.querySelector('#t tbody');
for(const label of DATA.labels){{
 const tr=document.createElement('tr');
 const td0=document.createElement('td');td0.textContent=label;tr.appendChild(td0);
 for(const style of ['bold','roman','italic']){{
   const td=document.createElement('td');
   const rows=(DATA.groups[label]&&DATA.groups[label][style])||[];
   if(!rows.length){{td.innerHTML='<span class="empty">saknas</span>';}}
   else{{
     const wrap=document.createElement('div');wrap.className='variants';
     rows.forEach((g,i)=>{{
       const box=document.createElement('div');box.className='variant';
       const cap=document.createElement('div');cap.className='cap';cap.textContent=(rows.length>1?'variant '+(i+1)+'/'+rows.length+' · ':'')+(g.sources?.length||0)+' källor';
       const c=document.createElement('canvas');drawGlyph(c,g);
       box.append(cap,c);wrap.appendChild(box);
     }});
     td.appendChild(wrap);
   }}
   tr.appendChild(td);
 }}
 tb.appendChild(tr);
}}
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render canonical SAOL glyph facit as a passive HTML table.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text(build_html(args.facit), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
