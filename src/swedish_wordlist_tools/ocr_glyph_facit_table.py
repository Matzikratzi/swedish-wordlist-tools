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
    for glyph in facit.get("glyphs") or []:
        label = str(glyph.get("label") or "")
        style = str(glyph.get("style") or "roman")
        if not label:
            continue
        groups[label][style].append(glyph)

    labels = sorted(groups, key=_sort_key)
    payload = {"labels": labels, "groups": groups}
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
<div class='meta'>En rad per etikett. Kolumner: fet, roman, kursiv. Alla sparade rastervarianter visas separat med modellens y=0 som stödlinje.</div>
<table id='t'>
<thead><tr><th>Glyph</th><th>Fet</th><th>Roman</th><th>Kursiv</th></tr></thead>
<tbody></tbody>
</table>
<script>
const DATA={data};
const SCALE=10, PAD=3;
function drawGlyph(canvas,g){{
 const pts=g.pixels_relative_to_baseline||[];
 if(!pts.length)return;
 const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
 const minx=Math.min(...xs), maxx=Math.max(...xs), miny=Math.min(...ys), maxy=Math.max(...ys);
 const y0=Math.min(miny,-2), y1=Math.max(maxy,2);
 const w=maxx-minx+1, h=y1-y0+1;
 canvas.width=(w+2*PAD)*SCALE; canvas.height=(h+2*PAD)*SCALE;
 const ctx=canvas.getContext('2d');
 ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
 for(const [x,y] of pts){{ctx.fillStyle='#111';ctx.fillRect((x-minx+PAD)*SCALE,(y-y0+PAD)*SCALE,SCALE,SCALE);}}
 // guide directly underneath baseline pixels, same convention as old editor
 const gy=(0-y0+PAD+1)*SCALE;
 ctx.strokeStyle='#d33';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,gy);ctx.lineTo(canvas.width,gy);ctx.stroke();
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
