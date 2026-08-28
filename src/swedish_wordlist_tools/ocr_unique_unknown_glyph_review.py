from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _components(points: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
    out: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        comp = {seed}
        stack = [seed]
        while stack:
            x, y = stack.pop()
            for p in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if p in remaining:
                    remaining.remove(p)
                    comp.add(p)
                    stack.append(p)
        out.append(comp)
    return out


def _xspan(points: set[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in points]
    return min(xs), max(xs)


def _merge_overlapping_x(components: list[set[tuple[int, int]]]) -> list[set[tuple[int, int]]]:
    """Merge detached parts that plausibly belong to one glyph.

    Dots, rings and accents are disconnected from their bodies but normally
    overlap the body's horizontal span.  No transcription is used here.
    """
    groups = [set(c) for c in components]
    changed = True
    while changed:
        changed = False
        out: list[set[tuple[int, int]]] = []
        while groups:
            current = groups.pop()
            a0, a1 = _xspan(current)
            rest: list[set[tuple[int, int]]] = []
            for other in groups:
                b0, b1 = _xspan(other)
                if max(a0, b0) <= min(a1, b1):
                    current.update(other)
                    a0, a1 = _xspan(current)
                    changed = True
                else:
                    rest.append(other)
            groups = rest
            out.append(current)
        groups = out
    return sorted(groups, key=lambda c: (_xspan(c)[0], min(y for _, y in c)))


def unknown_groups(row: dict[str, Any]) -> list[set[tuple[int, int]]]:
    points = {tuple(map(int, p)) for p in row.get("unexplained") or []}
    if not points:
        return []
    return _merge_overlapping_x(_components(points))


def _shape(points: set[tuple[int, int]], baseline: int) -> tuple[tuple[int, int], ...]:
    minx = min(x for x, _ in points)
    return tuple(sorted((x - minx, y - baseline) for x, y in points))


def collect_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_shape: dict[tuple[tuple[int, int], ...], dict[str, Any]] = {}
    seq = 0
    for row in rows:
        baseline = row.get("baseline")
        if not isinstance(baseline, int):
            continue
        for group in unknown_groups(row):
            shape = _shape(group, baseline)
            if not shape:
                continue
            source = {
                "expected_word": row.get("expected"),
                "page": row.get("page"),
                "subnr": row.get("subnr"),
                "source_id": (row.get("source") or {}).get("source_id"),
            }
            cand = by_shape.get(shape)
            if cand is None:
                seq += 1
                xs = [x for x, _ in group]
                ys = [y for _, y in group]
                cand = {
                    "id": seq,
                    "shape": [list(p) for p in shape],
                    "pixels": [list(p) for p in sorted(group)],
                    "baseline": baseline,
                    "width": max(xs) - min(xs) + 1,
                    "height": max(ys) - min(ys) + 1,
                    "occurrences": 0,
                    "sources": [],
                    "context": {
                        "expected": row.get("expected"),
                        "width": row.get("width"),
                        "height": row.get("height"),
                        "ink": row.get("ink") or [],
                        "exact": row.get("exact") or [],
                        "candidate_pixels": [list(p) for p in sorted(group)],
                        "baseline": baseline,
                    },
                }
                by_shape[shape] = cand
            cand["occurrences"] += 1
            if source not in cand["sources"]:
                cand["sources"].append(source)
    return sorted(by_shape.values(), key=lambda c: c["id"])


def build_html(rows: list[dict[str, Any]], facit_path: Path) -> str:
    facit = json.loads(facit_path.read_text(encoding="utf-8"))
    candidates = collect_candidates(rows)
    payload = json.dumps({"candidates": candidates, "facit": facit}, ensure_ascii=False)
    return f"""<!doctype html>
<meta charset='utf-8'>
<title>SAOL – okända glyphar</title>
<style>
body{{font-family:system-ui,sans-serif;margin:18px;background:#f4f4f4;color:#111}}
.top{{position:sticky;top:0;z-index:5;background:white;border:1px solid #bbb;padding:10px;margin-bottom:14px}}
.card{{background:white;border:1px solid #bbb;padding:12px;margin:12px 0}}
.card.done{{opacity:.45}}
canvas{{image-rendering:pixelated;border:1px solid #888;background:white;display:block;margin:8px 0}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
input,button{{font:inherit;padding:5px}} .meta{{color:#555;font-size:.92em}}
.badge{{font-weight:700}} .examples{{margin-top:4px}}
</style>
<div class='top'><b>SAOL – unika okända glyphar</b> <span id='stats'></span>
<button id='save'>Spara facit med godkända glyphar</button>
<div><small>Kända glyphar har redan lästs in. Här visas endast unika oförklarade rasterformer. Lila i kontexten = känd glyph, grönt = aktuell okänd kandidat.</small></div></div>
<div id='cards'></div>
<script>
const DATA={payload}; const SCALE=12,M=2; const additions=[]; const decisions=new Map();
const keyOf=g=>JSON.stringify([g.label,g.style,g.pixels_relative_to_baseline]);
const known=new Set(DATA.facit.glyphs.map(keyOf));
const styleMap={{b:'bold',r:'roman',i:'italic'}};
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));}}
function parseLabel(raw){{const s=raw.trim();const m=s.match(/^(.*)\\{{([bri])\\}}$/i);if(!m)return null;return{{label:m[1],style:styleMap[m[2].toLowerCase()]}};}}
function pkey(x,y){{return x+','+y;}}
function drawContext(canvas,c){{const row=c.context,ctx=canvas.getContext('2d');canvas.width=(row.width+2*M)*SCALE;canvas.height=(row.height+2*M)*SCALE;ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);const exact=new Set();for(const m of row.exact)for(const [x,y] of m.pixels)exact.add(pkey(x,y));const cur=new Set(row.candidate_pixels.map(([x,y])=>pkey(x,y)));for(const [x,y] of row.ink){{ctx.fillStyle=cur.has(pkey(x,y))?'#2a9d4b':(exact.has(pkey(x,y))?'#8f83d8':'#111');ctx.fillRect((x+M)*SCALE,(y+M)*SCALE,SCALE,SCALE);}}const by=(row.baseline+1+M)*SCALE;ctx.strokeStyle='#d33';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,by);ctx.lineTo(canvas.width,by);ctx.stroke();}}
function drawGlyph(canvas,c){{const pts=c.shape,ctx=canvas.getContext('2d');const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);const miny=Math.min(...ys),maxy=Math.max(...ys),w=Math.max(...xs)+1,h=maxy-miny+1;canvas.width=(w+4)*SCALE;canvas.height=(h+4)*SCALE;ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);for(const [x,y] of pts){{ctx.fillStyle='#111';ctx.fillRect((x+2)*SCALE,(y-miny+2)*SCALE,SCALE,SCALE);}}const by=(0-miny+2+1)*SCALE;ctx.strokeStyle='#d33';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,by);ctx.lineTo(canvas.width,by);ctx.stroke();}}
function stats(){{const done=decisions.size;document.getElementById('stats').textContent=' · '+DATA.candidates.length+' unika raster · '+done+' behandlade · '+additions.length+' godkända';}}
const root=document.getElementById('cards');
for(const c of DATA.candidates){{const d=document.createElement('div');d.className='card';d.innerHTML='<span class="badge">Okänd #'+c.id+'</span> <span class="meta">'+c.occurrences+' förekomst(er)</span><div class="examples">Exempel: '+c.sources.slice(0,8).map(s=>esc(s.expected_word)+' (sida '+esc(s.page)+')').join(', ')+'</div>';const g=document.createElement('canvas');drawGlyph(g,c);d.appendChild(g);const ctx=document.createElement('canvas');drawContext(ctx,c);d.appendChild(ctx);const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input size="10" placeholder="é{{r}}"></label><button class="approve">Godkänn</button><button class="skip">Hoppa över</button><span class="msg"></span>';d.appendChild(ctrl);const input=ctrl.querySelector('input');ctrl.querySelector('.approve').onclick=()=>{{const p=parseLabel(input.value);if(!p||!p.label){{ctrl.querySelector('.msg').textContent='Skriv etikett med stil, t.ex. é{{r}}, A{{b}} eller f{{i}}.';return;}}const glyph={{label:p.label,style:p.style,pixels_relative_to_baseline:c.shape,sources:c.sources}};const k=keyOf(glyph);if(!known.has(k)&&!additions.some(a=>keyOf(a)===k))additions.push(glyph);decisions.set(c.id,'approved');d.classList.add('done');ctrl.querySelector('.msg').textContent='Godkänd.';stats();}};ctrl.querySelector('.skip').onclick=()=>{{decisions.set(c.id,'skipped');d.classList.add('done');ctrl.querySelector('.msg').textContent='Överhoppad.';stats();}};root.appendChild(d);}}
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};stats();
</script>"""
