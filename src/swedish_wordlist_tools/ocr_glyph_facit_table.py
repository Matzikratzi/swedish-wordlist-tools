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
    payload = {
        "labels": labels,
        "groups": groups,
        "global_min_y": min(all_ys + [-2]),
        "global_max_y": max(all_ys + [2]),
        "facit": facit,
    }
    data = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL glyphfacit – jämförelse</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f6f6f6;color:#111}}
h1{{margin:0 0 8px}} .meta{{color:#555;margin-bottom:12px}}
.toolbar{{position:sticky;top:0;z-index:20;background:#f6f6f6;padding:8px 0 10px;display:flex;gap:10px;align-items:center}}
.toolbar button{{padding:7px 12px}}
#status{{font-size:13px;color:#555}}
#header,#rows{{min-width:max-content}}
.header-row,.glyph-row{{display:grid;grid-template-columns:64px var(--bold-w) var(--roman-w) var(--italic-w);column-gap:24px;align-items:start}}
.header-row{{position:sticky;top:52px;z-index:5;background:#f6f6f6;padding:8px 0 10px;border-bottom:1px solid #ccc;font-weight:700}}
.glyph-row{{padding:7px 0}}
.label{{font-size:26px;font-weight:700;text-align:center;padding-top:18px}}
.style-zone{{display:flex;gap:12px;align-items:flex-start;min-height:1px}}
.variant{{display:flex;flex-direction:column;align-items:flex-start;padding:4px;border:2px solid transparent;border-radius:6px}}
.variant.provisional{{border-style:dashed;border-color:#999;background:#fff}}
.variant.approved{{border-style:solid;border-color:#777}}
.variant.rejected{{opacity:.35;text-decoration:line-through}}
.cap{{font-size:11px;color:#666;min-height:16px;white-space:nowrap}}
.badge{{font-size:11px;font-weight:700;margin-bottom:3px}}
.sources{{font-size:10px;color:#555;max-width:220px;white-space:normal;margin-top:4px}}
.review{{display:flex;gap:5px;margin-top:5px}}
.review button{{font-size:11px;padding:3px 7px}}
canvas{{image-rendering:pixelated;display:block;background:white}}
.empty{{color:#bbb;font-size:12px;padding-top:30px}}
</style>
<h1>SAOL glyphfacit</h1>
<div class='meta'>Gamla facitmodeller visas utan ram. Automatiskt skördade modeller är märkta <b>NY – preliminär</b> och kan godkännas eller underkännas. Exporten tar bort underkända preliminära modeller men lämnar gamla modeller orörda.</div>
<div class='toolbar'><button id='export'>Exportera granskad JSON</button><button id='reset'>Återställ val</button><span id='status'></span></div>
<div id='header'></div><div id='rows'></div>
<script>
const DATA={data};
const SCALE=12, PADX=2, PADY=2, VARIANT_GAP=12;
const GLOBAL_MIN_Y=DATA.global_min_y, GLOBAL_MAX_Y=DATA.global_max_y;
const GLOBAL_H=GLOBAL_MAX_Y-GLOBAL_MIN_Y+1;
let seq=0; const decisions=new Map();

function glyphWidth(g){{ const pts=g.pixels_relative_to_baseline||[]; if(!pts.length)return 0; const xs=pts.map(p=>p[0]); return (Math.max(...xs)-Math.min(...xs)+1+2*PADX)*SCALE; }}
function groupWidth(rows){{ if(!rows.length)return 0; return rows.reduce((s,g)=>s+glyphWidth(g),0)+VARIANT_GAP*(rows.length-1); }}
const styleWidths={{}};
for(const style of ['bold','roman','italic']){{ let w=80; for(const label of DATA.labels){{ const rows=(DATA.groups[label]&&DATA.groups[label][style])||[]; w=Math.max(w,groupWidth(rows)); }} styleWidths[style]=w; }}
document.documentElement.style.setProperty('--bold-w',styleWidths.bold+'px'); document.documentElement.style.setProperty('--roman-w',styleWidths.roman+'px'); document.documentElement.style.setProperty('--italic-w',styleWidths.italic+'px');

function drawGlyph(canvas,g){{
 const pts=g.pixels_relative_to_baseline||[]; if(!pts.length)return;
 const xs=pts.map(p=>p[0]); const minx=Math.min(...xs), maxx=Math.max(...xs), w=maxx-minx+1;
 canvas.width=(w+2*PADX)*SCALE; canvas.height=(GLOBAL_H+2*PADY)*SCALE; const ctx=canvas.getContext('2d');
 ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height); ctx.strokeStyle='#ddd';ctx.lineWidth=1;
 for(let gx=0;gx<=w+2*PADX;gx++){{ const xx=gx*SCALE+0.5;ctx.beginPath();ctx.moveTo(xx,0);ctx.lineTo(xx,canvas.height);ctx.stroke(); }}
 for(let gy=0;gy<=GLOBAL_H+2*PADY;gy++){{ const yy=gy*SCALE+0.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(canvas.width,yy);ctx.stroke(); }}
 for(const [x,y] of pts){{ ctx.fillStyle='#111';ctx.fillRect((x-minx+PADX)*SCALE,(y-GLOBAL_MIN_Y+PADY)*SCALE,SCALE,SCALE); }}
 const baselineY=(0-GLOBAL_MIN_Y+PADY+1)*SCALE; ctx.strokeStyle='#d33';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,baselineY);ctx.lineTo(canvas.width,baselineY);ctx.stroke();
}}
function sourceText(g){{
 const src=g.sources||[]; if(!src.length)return '';
 const d=[...new Set(src.filter(s=>s.harvest_half==='discover').map(s=>s.expected_word).filter(Boolean))];
 const v=[...new Set(src.filter(s=>s.harvest_half==='verify').map(s=>s.expected_word).filter(Boolean))];
 let parts=[]; if(d.length)parts.push('hittad: '+d.join(', ')); if(v.length)parts.push('verifierad: '+v.join(', ')); return parts.join(' · ');
}}
function updateStatus(){{ let a=0,r=0,u=0; for(const el of document.querySelectorAll('.variant.provisional')){{ const d=decisions.get(el.dataset.reviewId); if(d==='approve')a++; else if(d==='reject')r++; else u++; }} document.getElementById('status').textContent=`nya: ${{a}} godkända, ${{r}} underkända, ${{u}} ogranskade`; }}
function setDecision(el,id,val){{ decisions.set(id,val); el.classList.toggle('approved',val==='approve'); el.classList.toggle('rejected',val==='reject'); updateStatus(); }}

const header=document.getElementById('header'); const hr=document.createElement('div');hr.className='header-row'; for(const text of ['','Fet','Roman','Kursiv']){{const d=document.createElement('div');d.textContent=text;hr.appendChild(d);}} header.appendChild(hr);
const root=document.getElementById('rows');
for(const label of DATA.labels){{
 const row=document.createElement('div');row.className='glyph-row'; const lab=document.createElement('div');lab.className='label';lab.textContent=label;row.appendChild(lab);
 for(const style of ['bold','roman','italic']){{
   const zone=document.createElement('div');zone.className='style-zone'; const models=(DATA.groups[label]&&DATA.groups[label][style])||[];
   if(!models.length){{const e=document.createElement('div');e.className='empty';e.textContent='–';zone.appendChild(e);}}
   else models.forEach((g,i)=>{{
     const v=document.createElement('div');v.className='variant'+(g.provisional?' provisional':''); const id='g'+(++seq); v.dataset.reviewId=id; g.__review_id=id;
     const cap=document.createElement('div');cap.className='cap';cap.textContent=models.length>1?('variant '+(i+1)+'/'+models.length):''; v.appendChild(cap);
     if(g.provisional){{ const badge=document.createElement('div');badge.className='badge';badge.textContent='NY – preliminär';v.appendChild(badge); }}
     const c=document.createElement('canvas');drawGlyph(c,g);v.appendChild(c);
     const st=sourceText(g); if(st){{const s=document.createElement('div');s.className='sources';s.textContent=st;v.appendChild(s);}}
     if(g.provisional){{ const rev=document.createElement('div');rev.className='review'; const ok=document.createElement('button');ok.textContent='Godkänn';ok.onclick=()=>setDecision(v,id,'approve'); const no=document.createElement('button');no.textContent='Underkänn';no.onclick=()=>setDecision(v,id,'reject'); rev.append(ok,no);v.appendChild(rev); }}
     zone.appendChild(v);
   }});
   row.appendChild(zone);
 }} root.appendChild(row);
}}
updateStatus();

document.getElementById('reset').onclick=()=>{{decisions.clear();for(const el of document.querySelectorAll('.variant'))el.classList.remove('approved','rejected');updateStatus();}};
document.getElementById('export').onclick=()=>{{
 const out=structuredClone(DATA.facit); out.glyphs=(out.glyphs||[]).filter(g=>!g.provisional || decisions.get(g.__review_id)!=='reject').map(g=>{{const x={{...g}};delete x.__review_id;if(x.provisional && decisions.get(g.__review_id)==='approve'){{x.review={{status:'approved-in-html'}};}}return x;}});
 out.review={{source:'glyph-facit-table-auto.html', rejected_provisional:[...decisions.entries()].filter(([,v])=>v==='reject').map(([k])=>k)}};
 const blob=new Blob([JSON.stringify(out,null,2)+'\n'],{{type:'application/json'}}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='glyph-facit-auto-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}};
</script>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render canonical SAOL glyph facit as an aligned HTML overview/reviewer.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.write_text(build_html(args.facit), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
