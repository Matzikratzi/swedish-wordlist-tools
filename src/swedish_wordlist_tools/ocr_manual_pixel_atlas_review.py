from __future__ import annotations

import argparse
import base64
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _greedy_words(words: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    """Prefer words that add rare characters while keeping both styles represented."""
    if limit <= 0 or len(words) <= limit:
        return words
    freq: Counter[tuple[str, str]] = Counter()
    for w in words:
        style = str(w.get("style") or "")
        for ch in set(str(w.get("expected_word") or "")):
            freq[(style, ch)] += 1

    selected: list[dict[str, object]] = []
    seen: Counter[tuple[str, str]] = Counter()
    remaining = list(words)
    while remaining and len(selected) < limit:
        def score(w: dict[str, object]) -> tuple[float, int]:
            style = str(w.get("style") or "")
            text = str(w.get("expected_word") or "")
            gain = 0.0
            for ch in set(text):
                key = (style, ch)
                gain += 1.0 / (1.0 + seen[key])
                gain += 0.35 / max(1, freq[key])
            return gain, len(text)
        best = max(remaining, key=score)
        remaining.remove(best)
        selected.append(best)
        style = str(best.get("style") or "")
        for ch in set(str(best.get("expected_word") or "")):
            seen[(style, ch)] += 1
    return selected


def _atlas_examples(path: Path | None) -> tuple[dict[str, dict[str, list[list[list[int]]]]], dict[str, Counter[str]]]:
    """Load baseline-normalized pixel shapes from a previous manual atlas."""
    examples: dict[str, dict[str, list[list[list[int]]]]] = defaultdict(lambda: defaultdict(list))
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    if path is None:
        return {}, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    for word in payload.get("words", []):
        if not isinstance(word, dict):
            continue
        style = str(word.get("style") or "")
        baseline = int(word.get("baseline_y", 0))
        for ann in word.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            label = str(ann.get("label") or "")
            raw = ann.get("pixels")
            if not label or not isinstance(raw, list) or not raw:
                continue
            pts = [(int(p[0]), int(p[1])) for p in raw if isinstance(p, list) and len(p) == 2]
            if not pts:
                continue
            xmin = min(x for x, _ in pts)
            shape = sorted([[x - xmin, y - baseline] for x, y in pts], key=lambda p: (p[1], p[0]))
            examples[style][label].append(shape)
            counts[style][label] += 1
    return {s: dict(v) for s, v in examples.items()}, dict(counts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a pixel-perfect manual glyph/cluster annotation editor.")
    ap.add_argument("library", type=Path, help="Mixed-style word-segment library")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--scale", type=int, default=18, help="Displayed size of one original raster pixel")
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--atlas", type=Path, help="Previous manual pixel atlas; used for coverage and exact-shape comparison")
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    words = [w for w in manifest.get("words", []) if isinstance(w, dict)]
    if args.style:
        words = [w for w in words if w.get("style") == args.style]
    words = [w for w in words if isinstance(w.get("word_file"), str) and (args.library / str(w["word_file"])).exists()]
    words = _greedy_words(words, args.limit)
    reference_examples, reference_counts = _atlas_examples(args.atlas)

    cards: list[str] = []
    for n, w in enumerate(words):
        rel = str(w["word_file"])
        path = args.library / rel
        with Image.open(path) as im:
            width, height = im.size
        expected = str(w.get("expected_word") or "")
        headword = str(w.get("headword") or "")
        style = str(w.get("style") or "")
        source_id = str(w.get("source_id") or "")
        page = str(w.get("page") or "")
        subnr = str(w.get("subnr") or "")
        baseline = max(0, height - 2)
        cards.append(f'''
<article class="card" data-n="{n}" data-source-id="{html.escape(source_id, quote=True)}"
 data-style="{html.escape(style, quote=True)}" data-expected="{html.escape(expected, quote=True)}"
 data-headword="{html.escape(headword, quote=True)}" data-word-file="{html.escape(rel, quote=True)}"
 data-page="{html.escape(page, quote=True)}" data-subnr="{html.escape(subnr, quote=True)}"
 data-w="{width}" data-h="{height}" data-baseline="{baseline}">
 <header><strong>{html.escape(expected)}</strong><span class="badge">{html.escape(style)}</span>
 <span>uppslagsord: <b>{html.escape(headword) if headword else '(saknas i denna batch)'}</b></span>
 <span>sida {html.escape(page)} · subnr {html.escape(subnr)}</span></header>
 <div class="controls">
   <label>Etikett <input class="label" size="8" placeholder="a / i / st"></label>
   <button class="erase" type="button">Sudd: av</button>
   <label>Baslinje y=<input class="baseline" type="number" min="0" max="{height-1}" value="{baseline}"></label>
   <button class="baseup" type="button">−1</button><button class="basedown" type="button">+1</button>
   <button class="clear" type="button">Rensa ordet</button>
   <span class="count">0 märkta pixlar</span>
 </div>
 <div class="canvaswrap"><canvas width="{width * max(4,args.scale)}" height="{height * max(4,args.scale)}"></canvas></div>
 <img class="source" src="{_data_uri(path)}" alt="" hidden>
 <div class="legend"></div><div class="comparison"></div>
</article>''')

    coverage_parts: list[str] = []
    for style in ("italic", "roman"):
        counts = reference_counts.get(style, Counter())
        if not counts:
            continue
        glyphs = [(k, v) for k, v in counts.items() if len(k) == 1]
        clusters = [(k, v) for k, v in counts.items() if len(k) > 1]
        def chips(items: list[tuple[str, int]]) -> str:
            return " ".join(f'<span class="covchip"><b>{html.escape(k)}</b> ×{v}</span>' for k, v in sorted(items)) or '<span class="none">inga</span>'
        coverage_parts.append(f'<div class="covstyle"><b>{style}</b> · glypher: {chips(glyphs)}<br>kluster: {chips(clusters)}</div>')
    coverage = ''.join(coverage_parts) or '<div class="none">Ingen tidigare atlas laddad.</div>'

    scale = max(4, args.scale)
    refs_json = json.dumps(reference_examples, ensure_ascii=False)
    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL pixelatlas</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:20px;background:#f3f3f3;color:#161616}}
.toolbar{{position:sticky;top:0;z-index:20;background:#f3f3f3ee;padding:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
.coverage{{background:#fff;border:1px solid #bbb;border-radius:8px;padding:10px;margin:10px 0}}.covstyle{{margin:5px 0;line-height:1.9}}.covchip{{display:inline-block;background:#edf2f7;border:1px solid #ccd5df;border-radius:999px;padding:0 6px;margin:1px 2px;font-size:12px}}.none{{color:#777}}
.card{{background:white;border:1px solid #bbb;border-radius:9px;padding:12px;margin:14px 0}}header{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px;text-transform:uppercase}}
.controls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}input,button{{font:inherit}}.label{{font-size:18px;font-weight:700}}.canvaswrap{{overflow:auto;max-width:100%;border:1px solid #999;background:#ddd;display:inline-block}}canvas{{display:block;image-rendering:pixelated;cursor:crosshair;touch-action:none}}
.legend{{font-size:12px;margin-top:6px;display:flex;gap:8px;flex-wrap:wrap}}.swatch{{padding:2px 6px;border-radius:4px;color:white;text-shadow:0 1px 2px #000}}.count{{color:#555;font-size:12px}}.comparison{{margin-top:6px;font-size:13px;line-height:1.5}}.exact{{color:#08752b;font-weight:800}}.near{{color:#8a5b00}}.new{{color:#555}}#q{{width:24rem;max-width:80vw;padding:.4rem}}.hidden{{display:none}}
</style>
<h1>SAOL manuell pixelatlas</h1>
<p>Varje klick färgar exakt <b>en originalpixel</b>. Formen jämförs mot tidigare facit efter x-normalisering och relativt baslinjen. Därför betyder <b>PIXELIDENTISK</b> verkligen samma märkta rasterform i samma stil.</p>
<div class="coverage"><b>Befintligt pixel-facit</b>{coverage}</div>
<div class="toolbar"><input id="q" placeholder="Filtrera ord / uppslagsord / stil"><button id="export">Exportera pixelatlas</button><span id="global"></span></div>
{''.join(cards)}
<script>
const SCALE={scale};
const REFS={refs_json};
const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];
function colorFor(label){{let h=0;for(const c of label)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length];}}
const states=new Map();
function key(x,y){{return x+','+y}}
function normalizedShape(points,baseline){{if(!points.length)return [];let xmin=Math.min(...points.map(p=>p[0]));return points.map(([x,y])=>[x-xmin,y-baseline]).sort((a,b)=>a[1]-b[1]||a[0]-b[0]);}}
function shapeKey(shape){{return shape.map(p=>p[0]+','+p[1]).join(';')}}
function symdiff(a,b){{const A=new Set(a.map(p=>p[0]+','+p[1])),B=new Set(b.map(p=>p[0]+','+p[1]));let n=0;for(const x of A)if(!B.has(x))n++;for(const x of B)if(!A.has(x))n++;return n;}}
function currentExamples(skipCard,style,label){{const out=[];for(const [card,s] of states){{if(card===skipCard||card.dataset.style!==style)continue;const pts=[];for(const [k,l] of s.pixels)if(l===label)pts.push(k.split(',').map(Number));if(pts.length)out.push(normalizedShape(pts,s.baseline));}}return out;}}
function compareCard(card,state){{const by={{}};for(const [k,l] of state.pixels)(by[l]??=[]).push(k.split(',').map(Number));const lines=[];for(const label of Object.keys(by).sort()){{const shape=normalizedShape(by[label],state.baseline),refs=[...(((REFS[card.dataset.style]||{{}})[label])||[]),...currentExamples(card,card.dataset.style,label)];if(!refs.length){{lines.push('<span class="new"><b>'+label+'</b>: inget tidigare pixel-facit</span>');continue;}}const k=shapeKey(shape),exact=refs.filter(r=>shapeKey(r)===k).length;if(exact)lines.push('<span class="exact"><b>'+label+'</b>: PIXELIDENTISK med '+exact+' tidigare exempel</span>');else{{const ds=refs.map(r=>symdiff(shape,r));const best=Math.min(...ds);lines.push('<span class="near"><b>'+label+'</b>: inte identisk · närmast skiljer '+best+' pixlar · '+refs.length+' tidigare exempel</span>');}}}}card.querySelector('.comparison').innerHTML=lines.join('<br>');}}
function setup(card){{
 const canvas=card.querySelector('canvas'),ctx=canvas.getContext('2d'),img=card.querySelector('.source');
 const W=+card.dataset.w,H=+card.dataset.h;
 const state={{pixels:new Map(),baseline:+card.dataset.baseline,erase:false,drag:false,last:null}};states.set(card,state);
 function render(){{
  ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,W*SCALE,H*SCALE);
  ctx.lineWidth=1;ctx.strokeStyle='rgba(100,100,100,.20)';for(let x=0;x<=W;x++){{ctx.beginPath();ctx.moveTo(x*SCALE+.5,0);ctx.lineTo(x*SCALE+.5,H*SCALE);ctx.stroke();}}for(let y=0;y<=H;y++){{ctx.beginPath();ctx.moveTo(0,y*SCALE+.5);ctx.lineTo(W*SCALE,y*SCALE+.5);ctx.stroke();}}
  for(const [k,label] of state.pixels){{const [x,y]=k.split(',').map(Number);ctx.fillStyle=colorFor(label)+'aa';ctx.fillRect(x*SCALE,y*SCALE,SCALE,SCALE);}}
  ctx.strokeStyle='#e00000';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,(state.baseline+1)*SCALE);ctx.lineTo(W*SCALE,(state.baseline+1)*SCALE);ctx.stroke();
  card.querySelector('.count').textContent=state.pixels.size+' märkta pixlar';const labels=[...new Set(state.pixels.values())].sort();card.querySelector('.legend').innerHTML=labels.map(l=>'<span class="swatch" style="background:'+colorFor(l)+'">'+l+'</span>').join('');compareCard(card,state);refreshGlobal();
 }}
 function pos(ev){{const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(W-1,Math.floor((ev.clientX-r.left)/SCALE))),Math.max(0,Math.min(H-1,Math.floor((ev.clientY-r.top)/SCALE)))];}}
 function paint(ev){{const [x,y]=pos(ev),k=key(x,y);if(state.last===k&&state.drag)return;state.last=k;if(state.erase||ev.altKey)state.pixels.delete(k);else{{const label=card.querySelector('.label').value.trim();if(!label)return;const old=state.pixels.get(k);if(!state.drag&&old===label)state.pixels.delete(k);else state.pixels.set(k,label);}}render();}}
 canvas.addEventListener('pointerdown',e=>{{state.drag=false;state.last=null;canvas.setPointerCapture(e.pointerId);paint(e);state.drag=true;}});canvas.addEventListener('pointermove',e=>{{if(state.drag)paint(e);}});canvas.addEventListener('pointerup',()=>{{state.drag=false;state.last=null;}});
 const b=card.querySelector('.baseline');b.onchange=()=>{{state.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=state.baseline;render();}};card.querySelector('.baseup').onclick=()=>{{b.value=Math.max(0,state.baseline-1);b.onchange();}};card.querySelector('.basedown').onclick=()=>{{b.value=Math.min(H-1,state.baseline+1);b.onchange();}};
 const er=card.querySelector('.erase');er.onclick=()=>{{state.erase=!state.erase;er.textContent='Sudd: '+(state.erase?'på':'av');}};card.querySelector('.clear').onclick=()=>{{if(confirm('Rensa alla märkta pixlar i detta ord?')){{state.pixels.clear();render();}}}};if(img.complete)render();else img.onload=render;
}}
function refreshGlobal(){{let p=0,w=0;for(const [card,s] of states){{p+=s.pixels.size;if(s.pixels.size)w++;}}document.querySelector('#global').textContent=w+' ord · '+p+' märkta pixlar';}}
document.querySelectorAll('.card').forEach(setup);
const q=document.querySelector('#q');q.oninput=()=>{{const s=q.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>{{const t=(c.dataset.expected+' '+c.dataset.headword+' '+c.dataset.style+' '+c.dataset.page).toLowerCase();c.classList.toggle('hidden',!t.includes(s));}})}};
document.querySelector('#export').onclick=()=>{{const words=[];for(const [card,s] of states){{if(!s.pixels.size)continue;const byLabel={{}};for(const [k,label] of s.pixels){{const xy=k.split(',').map(Number);(byLabel[label]??=[]).push(xy);}}const annotations=Object.entries(byLabel).map(([label,pixels])=>({{label,pixels:pixels.sort((a,b)=>a[1]-b[1]||a[0]-b[0])}}));words.push({{source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile,width:+card.dataset.w,height:+card.dataset.h,baseline_y:s.baseline,annotations}});}}const out={{format:'saol-manual-pixel-atlas-v1',coordinate_system:'word crop pixels, origin top-left; baseline_y is last row above the red baseline edge',words}};const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-pixel-atlas.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(words)} scale={scale} reference_atlas={args.atlas or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
