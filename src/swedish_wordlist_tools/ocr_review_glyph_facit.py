from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

FORMAT = "saol14-manual-glyph-facit-v1"
STYLE_ORDER = {"bold": 0, "italic": 1, "roman": 2}


def _model_id(index: int, glyph: dict[str, Any]) -> str:
    return f"m{index:04d}-{glyph.get('style','roman')}-{glyph.get('label','')}"


def build_html(facit: dict[str, Any], source_name: str, scale: int = 18, margin: int = 2) -> str:
    glyphs = list(facit.get("glyphs") or [])
    indexed = list(enumerate(glyphs))
    indexed.sort(key=lambda it: (
        STYLE_ORDER.get(str(it[1].get("style") or "roman"), 99),
        str(it[1].get("label") or ""),
        it[0],
    ))

    cards: list[str] = []
    for display_no, (orig_index, g) in enumerate(indexed, start=1):
        label = str(g.get("label") or "")
        style = str(g.get("style") or "roman")
        pts = [(int(x), int(y)) for x, y in (g.get("pixels_relative_to_baseline") or [])]
        if not pts:
            continue
        min_x = min(x for x, _ in pts)
        max_x = max(x for x, _ in pts)
        min_y = min(y for _, y in pts)
        max_y = max(y for _, y in pts)
        # Baseline y=0 must always be visible, even for all-above/all-below models.
        draw_min_y = min(min_y, 0) - margin
        draw_max_y = max(max_y, 0) + margin
        draw_min_x = min_x - margin
        draw_max_x = max_x + margin
        w = (draw_max_x - draw_min_x + 1) * scale
        h = (draw_max_y - draw_min_y + 1) * scale
        baseline_canvas_y = (0 - draw_min_y + 1) * scale
        sources = g.get("sources") or []
        mid = _model_id(orig_index, g)
        cards.append(f'''<article class="card" data-index="{orig_index}" data-id="{html.escape(mid)}" data-style="{html.escape(style)}" data-label="{html.escape(label)}">
  <div class="meta"><b>{html.escape(label)}</b> <span class="style">{html.escape(style)}</span> <span class="count">modell {display_no}/{len(indexed)} · {len(pts)} pixlar · {len(sources)} källor</span></div>
  <canvas width="{w}" height="{h}" data-scale="{scale}" data-minx="{draw_min_x}" data-miny="{draw_min_y}" data-baseliney="{baseline_canvas_y}" data-points='{html.escape(json.dumps(pts, separators=(",", ":")))}'></canvas>
  <div class="actions"><button class="reject" type="button">Underkänn</button><button class="undo" type="button" disabled>Ångra</button></div>
  <details><summary>Källor</summary><pre>{html.escape(json.dumps(sources, ensure_ascii=False, indent=2))}</pre></details>
</article>''')

    payload = json.dumps(facit, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><title>SAOL glyph-facitgranskning</title>
<style>
body{{font-family:system-ui,sans-serif;margin:20px;background:#f5f5f5;color:#111}}h1{{margin-bottom:.25rem}}
.toolbar{{position:sticky;top:0;z-index:5;background:#fff;border:1px solid #ccc;padding:10px;margin:12px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.section{{font-size:1.3rem;margin:30px 0 8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:10px}}.card.rejected{{opacity:.35;background:#fee;text-decoration:none}}
.meta{{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}}.meta b{{font-size:1.5rem}}.style{{font-family:monospace}}.count{{font-size:.8rem;color:#555}}
canvas{{display:block;margin:10px 0;border:1px solid #ddd;background:white;image-rendering:pixelated;max-width:100%}}
button{{font-size:1rem;padding:5px 10px}}button.reject{{font-weight:600}}pre{{white-space:pre-wrap;font-size:.75rem}}
</style></head><body>
<h1>SAOL glyph-facitgranskning</h1>
<p>En sparad modell per kort. Svarta rutor är modellens pixlar. Den röda linjen ligger exakt på den sparade stödlinjen <code>y=0</code>.</p>
<div class="toolbar"><b id="status"></b><button id="save" type="button">Spara rensat facit</button><button id="showRejected" type="button">Visa bara underkända</button><button id="showAll" type="button">Visa alla</button></div>
<div id="cards" class="grid">{''.join(cards)}</div>
<script id="facit" type="application/json">{payload}</script>
<script>
const facit=JSON.parse(document.getElementById('facit').textContent);const rejected=new Set();
function renderCanvas(c){{const ctx=c.getContext('2d'),s=+c.dataset.scale,minx=+c.dataset.minx,miny=+c.dataset.miny;ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#000';for(const [x,y] of JSON.parse(c.dataset.points)){{ctx.fillRect((x-minx)*s,(y-miny)*s,s,s);}}ctx.strokeStyle='#d00';ctx.lineWidth=2;const by=(0-miny+1)*s;ctx.beginPath();ctx.moveTo(0,by);ctx.lineTo(c.width,by);ctx.stroke();}}
for(const c of document.querySelectorAll('canvas'))renderCanvas(c);
function update(){{document.getElementById('status').textContent=`Godkända ${{facit.glyphs.length-rejected.size}} / ${{facit.glyphs.length}} · underkända ${{rejected.size}}`;}}
for(const card of document.querySelectorAll('.card')){{const i=+card.dataset.index,rej=card.querySelector('.reject'),undo=card.querySelector('.undo');rej.onclick=()=>{{rejected.add(i);card.classList.add('rejected');rej.disabled=true;undo.disabled=false;update();}};undo.onclick=()=>{{rejected.delete(i);card.classList.remove('rejected');rej.disabled=false;undo.disabled=true;update();}};}}
document.getElementById('showRejected').onclick=()=>{{for(const c of document.querySelectorAll('.card'))c.style.display=rejected.has(+c.dataset.index)?'block':'none';}};
document.getElementById('showAll').onclick=()=>{{for(const c of document.querySelectorAll('.card'))c.style.display='block';}};
document.getElementById('save').onclick=()=>{{const out=structuredClone(facit);out.glyphs=out.glyphs.filter((_,i)=>!rejected.has(i));out.review={{source:{json.dumps(source_name)},rejected_indices:[...rejected].sort((a,b)=>a-b),original_models:facit.glyphs.length,remaining_models:out.glyphs.length}};if(out.stats)out.stats.unique_label_style_shapes=out.glyphs.length;const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};update();
</script></body></html>'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a standalone browser reviewer for canonical SAOL glyph models.")
    ap.add_argument("facit", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=18)
    args = ap.parse_args()
    payload = json.loads(args.facit.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT:
        raise SystemExit(f"unsupported facit format: {payload.get('format')!r}")
    args.out.write_text(build_html(payload, str(args.facit), args.scale), encoding="utf-8")
    styles: dict[str,int] = {}
    for g in payload.get("glyphs") or []:
        st=str(g.get("style") or "roman");styles[st]=styles.get(st,0)+1
    print(f"models={len(payload.get('glyphs') or [])} styles={styles}")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
