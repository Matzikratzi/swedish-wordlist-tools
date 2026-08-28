from __future__ import annotations

import json
from collections import Counter
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
    """Merge detached marks with bodies, and preserve touching glyph clusters."""
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


def _nearest_style(row: dict[str, Any], group: set[tuple[int, int]]) -> str:
    gx0, gx1 = _xspan(group)
    gc = (gx0 + gx1) / 2
    best: tuple[float, str] | None = None
    for match in row.get("exact") or []:
        pixels = {tuple(p) for p in match.get("pixels") or []}
        if not pixels:
            continue
        x0, x1 = _xspan(pixels)
        dist = abs(((x0 + x1) / 2) - gc)
        style = str(match.get("style") or "")
        if style and (best is None or dist < best[0]):
            best = (dist, style)
    return best[1] if best else "bold"


def _suffix(style: str) -> str:
    return {"bold": "b", "roman": "r", "italic": "i"}.get(style, "b")


def _split_chunk(chunk: str, count: int) -> list[str]:
    if count <= 0:
        return []
    if count == 1:
        return [chunk]
    if len(chunk) == count:
        return list(chunk)
    # If JSONL says more/fewer characters than raster groups, do not invent a
    # confident split.  Put the cluster on the first group and leave the rest
    # unprefilled; the reviewer can correct it.
    return [chunk] + [""] * (count - 1)


def _jsonl_group_suggestions(row: dict[str, Any], groups: list[set[tuple[int, int]]]) -> list[str]:
    hint = row.get("jsonl_hint") or {}
    reference = str(hint.get("text") or "")
    if not reference or not groups:
        return [""] * len(groups)

    group_index = {id(g): i for i, g in enumerate(groups)}
    elements: list[tuple[int, str, Any]] = []
    for g in groups:
        elements.append((_xspan(g)[0], "unknown", g))
    for m in row.get("exact") or []:
        pixels = {tuple(p) for p in m.get("pixels") or []}
        if pixels and m.get("label"):
            elements.append((_xspan(pixels)[0], "known", m))
    elements.sort(key=lambda item: item[0])

    result = [""] * len(groups)
    cursor = 0
    pending: list[set[tuple[int, int]]] = []
    folded = reference.casefold()

    def assign(chunk: str) -> None:
        nonlocal pending
        pieces = _split_chunk(chunk, len(pending))
        for g, text in zip(pending, pieces):
            if text:
                result[group_index[id(g)]] = text
        pending = []

    for _, kind, obj in elements:
        if kind == "unknown":
            pending.append(obj)
            continue
        label = str(obj.get("label") or "")
        if not label:
            continue
        pos = folded.find(label.casefold(), cursor)
        if pos < 0:
            continue
        assign(reference[cursor:pos])
        cursor = pos + len(label)
    assign(reference[cursor:])

    # Attach visual style inferred from already exact neighbours.  This is a UI
    # suggestion only; pressing Godkänn is still required.
    for i, text in enumerate(result):
        if text:
            result[i] = f"{text}{{{_suffix(_nearest_style(row, groups[i]))}}}"
    return result


def collect_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_shape: dict[tuple[tuple[int, int], ...], dict[str, Any]] = {}
    seq = 0
    for row in rows:
        baseline = row.get("baseline")
        if not isinstance(baseline, int):
            continue
        groups = unknown_groups(row)
        suggestions = _jsonl_group_suggestions(row, groups)
        for group, suggestion in zip(groups, suggestions):
            shape = _shape(group, baseline)
            if not shape:
                continue
            hint = row.get("jsonl_hint") or {}
            source = {
                "expected_word": row.get("expected"),
                "jsonl_word": hint.get("text"),
                "jsonl_similarity": hint.get("similarity"),
                "page": row.get("page"),
                "subnr": row.get("subnr"),
                "source_id": (row.get("source") or {}).get("source_id"),
                "page_word_bbox": row.get("page_word_bbox"),
                "suggestion": suggestion,
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
                    "suggestion_counts": {},
                    "context": {
                        "expected": row.get("expected"),
                        "jsonl_hint": hint,
                        "page_word_bbox": row.get("page_word_bbox"),
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
            if suggestion:
                counts = Counter(cand.get("suggestion_counts") or {})
                counts[suggestion] += 1
                cand["suggestion_counts"] = dict(counts)

    candidates = sorted(by_shape.values(), key=lambda c: c["id"])
    for cand in candidates:
        counts = Counter(cand.get("suggestion_counts") or {})
        if counts:
            suggestion, support = counts.most_common(1)[0]
            cand["suggestion"] = suggestion
            cand["suggestion_support"] = support
        else:
            cand["suggestion"] = ""
            cand["suggestion_support"] = 0
    return candidates


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
.hint{{margin:5px 0;padding:5px;background:#fff8d8;border-left:4px solid #d7a600}}
.rasterdump{{display:none;white-space:pre;font:12px/1.05 monospace;background:#fafafa;border:1px solid #bbb;padding:8px;overflow:auto;max-width:100%;user-select:text}}
</style>
<div class='top'><b>SAOL – unika okända glyphar</b> <span id='stats'></span>
<button id='save'>Spara facit med godkända glyphar</button>
<div><small>Facitmatchning är primär. JSONL används endast som förskrivet förslag när rastret inte känns igen. Lila = känd glyph, grönt = aktuell kandidat.</small></div></div>
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
function rasterText(c){{const row=c.context;const ink=new Set((row.ink||[]).map(([x,y])=>pkey(x,y)));const exact=new Set();for(const m of (row.exact||[]))for(const [x,y] of m.pixels)exact.add(pkey(x,y));const cur=new Set((row.candidate_pixels||[]).map(([x,y])=>pkey(x,y)));const lines=[];lines.push('unknown_id='+c.id+' occurrences='+c.occurrences);lines.push('jsonl_suggestion='+String(c.suggestion||'')+' support='+String(c.suggestion_support||0));lines.push('jsonl_hint='+JSON.stringify(row.jsonl_hint||{{}}));lines.push('page_word_bbox='+JSON.stringify(row.page_word_bbox||null));lines.push('context_word='+String(row.expected??''));lines.push('size='+row.width+'x'+row.height+' baseline='+row.baseline);lines.push('candidate_shape_relative_to_baseline='+JSON.stringify(c.shape));lines.push('legend: #=other-unrecognized  X=known-exact  G=current-unknown  .=white');for(let y=0;y<row.height;y++){{let s=String(y).padStart(2,'0')+' ';for(let x=0;x<row.width;x++){{const k=pkey(x,y);s+=cur.has(k)?'G':(exact.has(k)?'X':(ink.has(k)?'#':'.'));}}lines.push(s+(y===row.baseline?'  < baseline':''));}}return lines.join('\\n');}}
function stats(){{const done=decisions.size;document.getElementById('stats').textContent=' · '+DATA.candidates.length+' unika raster · '+done+' behandlade · '+additions.length+' godkända';}}
const root=document.getElementById('cards');
for(const c of DATA.candidates){{const d=document.createElement('div');d.className='card';const hint=c.suggestion?'<div class="hint">JSONL-förslag: <b>'+esc(c.suggestion)+'</b> · stöd '+c.suggestion_support+'/'+c.occurrences+' förekomster</div>':'<div class="hint">Inget tillräckligt säkert JSONL-förslag för denna rasterform.</div>';d.innerHTML='<span class="badge">Okänd #'+c.id+'</span> <span class="meta">'+c.occurrences+' förekomst(er)</span>'+hint+'<div class="examples">Exempel: '+c.sources.slice(0,8).map(s=>esc(s.expected_word)+(s.jsonl_word?' → '+esc(s.jsonl_word):'')+' (sida '+esc(s.page)+')').join(', ')+'</div>';const g=document.createElement('canvas');drawGlyph(g,c);d.appendChild(g);const ctx=document.createElement('canvas');drawContext(ctx,c);d.appendChild(ctx);const ctrl=document.createElement('div');ctrl.className='controls';ctrl.innerHTML='<label>Etikett <input size="14" placeholder="é{{r}}" value="'+esc(c.suggestion||'')+'"></label><button class="approve">Godkänn</button><button class="skip">Hoppa över</button><button class="raster">Rastertext</button><span class="msg"></span>';d.appendChild(ctrl);const input=ctrl.querySelector('input');const dump=document.createElement('pre');dump.className='rasterdump';d.appendChild(dump);ctrl.querySelector('.raster').onclick=async()=>{{const text=rasterText(c);dump.textContent=text;dump.style.display='block';try{{await navigator.clipboard.writeText(text);ctrl.querySelector('.msg').textContent='Rastertext visad och kopierad.';}}catch(_){{ctrl.querySelector('.msg').textContent='Rastertext visad; markera den nedan för att kopiera.';}}}};ctrl.querySelector('.approve').onclick=()=>{{const p=parseLabel(input.value);if(!p||!p.label){{ctrl.querySelector('.msg').textContent='Skriv etikett med stil, t.ex. é{{r}}, A{{b}} eller f{{i}}.';return;}}const glyph={{label:p.label,style:p.style,pixels_relative_to_baseline:c.shape,sources:c.sources}};const k=keyOf(glyph);if(!known.has(k)&&!additions.some(a=>keyOf(a)===k))additions.push(glyph);decisions.set(c.id,'approved');d.classList.add('done');ctrl.querySelector('.msg').textContent='Godkänd.';stats();}};ctrl.querySelector('.skip').onclick=()=>{{decisions.set(c.id,'skipped');d.classList.add('done');ctrl.querySelector('.msg').textContent='Överhoppad.';stats();}};root.appendChild(d);}}
document.getElementById('save').onclick=()=>{{const out=structuredClone(DATA.facit);out.glyphs.push(...additions);out.glyphs.sort((a,b)=>a.style.localeCompare(b.style)||a.label.localeCompare(b.label)||JSON.stringify(a.pixels_relative_to_baseline).localeCompare(JSON.stringify(b.pixels_relative_to_baseline)));const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-facit-reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};stats();
</script>"""
