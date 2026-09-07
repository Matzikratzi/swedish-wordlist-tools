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


def _guess_baseline(path: Path, threshold: int = 210) -> tuple[int, float]:
    im = Image.open(path).convert("L")
    lows: list[int] = []
    for x in range(im.width):
        ys = [y for y in range(im.height) if im.getpixel((x, y)) < threshold]
        if ys:
            lows.append(max(ys))
    if not lows:
        return max(0, im.height - 2), 0.0
    counts = Counter(lows)
    scores = {
        y: counts.get(y - 1, 0) + 2 * counts.get(y, 0) + counts.get(y + 1, 0)
        for y in range(im.height)
    }
    best = max(scores.values())
    candidates = [y for y, score in scores.items() if score >= best * 0.92]
    baseline = min(candidates) if candidates else max(scores, key=scores.get)
    confidence = counts.get(baseline, 0) / max(1, len(lows))
    return baseline, confidence


def _shape_record(points: list[tuple[int, int]], baseline: int) -> dict[str, object]:
    xmin = min(x for x, _ in points)
    ymin = min(y for _, y in points)
    shape = sorted([[x - xmin, y - ymin] for x, y in points], key=lambda p: (p[1], p[0]))
    return {"shape": shape, "baseline_offset": baseline - ymin}


def _load_atlas(path: Path | None):
    refs: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
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
            if not label or not isinstance(raw, list):
                continue
            pts = [(int(p[0]), int(p[1])) for p in raw if isinstance(p, list) and len(p) == 2]
            if pts:
                refs[style][label].append(_shape_record(pts, baseline))
                counts[style][label] += 1
    return {s: dict(v) for s, v in refs.items()}, dict(counts)


def _choose_words(words: list[dict[str, object]], limit: int, counts: dict[str, Counter[str]]) -> list[dict[str, object]]:
    if limit <= 0 or len(words) <= limit:
        return words
    freq = Counter()
    for w in words:
        style = str(w.get("style") or "")
        for ch in set(str(w.get("expected_word") or "")):
            freq[(style, ch)] += 1
    seen = Counter()
    chosen: list[dict[str, object]] = []
    remaining = list(words)
    while remaining and len(chosen) < limit:
        def score(w: dict[str, object]) -> float:
            style = str(w.get("style") or "")
            total = 0.0
            for ch in set(str(w.get("expected_word") or "")):
                total += 1.5 / (1 + counts.get(style, Counter()).get(ch, 0) + seen[(style, ch)])
                total += 0.3 / max(1, freq[(style, ch)])
            return total
        w = max(remaining, key=score)
        remaining.remove(w)
        chosen.append(w)
        style = str(w.get("style") or "")
        for ch in set(str(w.get("expected_word") or "")):
            seen[(style, ch)] += 1
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid manual atlas: box-select ink, then edit exact pixels.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--atlas", type=Path)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--scale", type=int, default=18)
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--ink-threshold", type=int, default=210)
    args = ap.parse_args()

    manifest_path = args.library / "manifest-style-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    refs, counts = _load_atlas(args.atlas)
    words = [w for w in manifest.get("words", []) if isinstance(w, dict)]
    if args.style:
        words = [w for w in words if w.get("style") == args.style]
    words = [w for w in words if isinstance(w.get("word_file"), str) and (args.library / str(w["word_file"])).exists()]
    words = _choose_words(words, args.limit, counts)
    scale = max(4, args.scale)

    cards: list[str] = []
    for w in words:
        rel = str(w["word_file"])
        path = args.library / rel
        with Image.open(path) as im:
            width, height = im.size
        baseline, confidence = _guess_baseline(path, args.ink_threshold)
        expected = str(w.get("expected_word") or "")
        headword = str(w.get("headword") or "")
        style = str(w.get("style") or "")
        cards.append(f'''<article class="card" data-source-id="{html.escape(str(w.get('source_id') or ''), quote=True)}" data-style="{html.escape(style, quote=True)}" data-expected="{html.escape(expected, quote=True)}" data-headword="{html.escape(headword, quote=True)}" data-word-file="{html.escape(rel, quote=True)}" data-page="{html.escape(str(w.get('page') or ''), quote=True)}" data-subnr="{html.escape(str(w.get('subnr') or ''), quote=True)}" data-w="{width}" data-h="{height}" data-baseline="{baseline}" data-baseline-confidence="{confidence:.4f}">
<header><strong>{html.escape(expected)}</strong><span class="badge">{html.escape(style)}</span><span>uppslagsord: <b>{html.escape(headword) if headword else '(saknas i denna batch)'}</b></span><span>sida {html.escape(str(w.get('page') or ''))} · subnr {html.escape(str(w.get('subnr') or ''))}</span></header>
<div class="controls"><label>Etikett <input class="label" size="8" placeholder="a / i / st"></label><button class="boxmode active" type="button">Boxläge</button><button class="pixelmode" type="button">Pixelläge</button><label>Bläck &lt; <input class="threshold" type="number" min="0" max="255" value="{args.ink_threshold}" size="4"></label><label>Baslinje y=<input class="baseline" type="number" min="0" max="{height-1}" value="{baseline}"></label><button class="up" type="button">−1</button><button class="down" type="button">+1</button><span class="baseinfo">auto {baseline} · conf {confidence:.2f}</span><button class="erase" type="button">Sudd: av</button><button class="clear" type="button">Rensa</button><span class="count"></span></div>
<div class="canvaswrap"><canvas width="{width*scale}" height="{height*scale}"></canvas></div><img class="src" src="{_data_uri(path)}" hidden><div class="legend"></div><div class="comparison"></div></article>''')

    coverage: list[str] = []
    for style in ("italic", "roman"):
        c = counts.get(style, Counter())
        if not c:
            continue
        glyphs = sorted((k, v) for k, v in c.items() if len(k) == 1)
        clusters = sorted((k, v) for k, v in c.items() if len(k) > 1)
        def chips(items):
            return " ".join(f'<span class="chip"><b>{html.escape(k)}</b>×{v}</span>' for k, v in items) or "inga"
        coverage.append(f'<div><b>{style}</b> · glypher: {chips(glyphs)}<br>kluster: {chips(clusters)}</div>')

    refs_json = json.dumps(refs, ensure_ascii=False)
    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL hybrid atlas v3</title>
<style>*{{box-sizing:border-box}}body{{font-family:system-ui;margin:20px;background:#f3f3f3;color:#171717}}.toolbar{{position:sticky;top:0;background:#f3f3f3ee;z-index:10;padding:8px 0;display:flex;gap:10px;flex-wrap:wrap}}.coverage,.card{{background:white;border:1px solid #bbb;border-radius:8px;padding:10px;margin:12px 0}}.chip{{display:inline-block;background:#eef2f7;border:1px solid #ccd5df;border-radius:999px;padding:0 5px;margin:1px 2px;font-size:12px}}header,.controls{{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px}}input,button{{font:inherit}}.label{{font-size:18px;font-weight:700}}.active{{font-weight:800;outline:2px solid #1479ff}}.canvaswrap{{display:inline-block;overflow:auto;max-width:100%;border:1px solid #999;background:#ddd}}canvas{{display:block;image-rendering:pixelated;cursor:crosshair;touch-action:none}}.legend{{margin-top:5px;display:flex;gap:6px;flex-wrap:wrap}}.swatch{{padding:2px 6px;border-radius:4px;color:white;text-shadow:0 1px 2px #000}}.comparison{{margin-top:6px;line-height:1.5;font-size:13px}}.exact{{color:#08752b;font-weight:800}}.near{{color:#8a5b00}}.basewarn{{color:#a33;font-weight:700}}.baseinfo,.count{{font-size:12px;color:#555}}#q{{width:25rem;max-width:80vw}}.hidden{{display:none}}</style>
<h1>SAOL hybrid pixelatlas v3</h1><p><b>Boxläge:</b> dra runt en glyph eller ett kluster; bara mörka pixlar i boxen markeras. <b>Pixelläge:</b> klicka för att lägga till eller ta bort en exakt originalpixel. Exporten innehåller råa pixelkoordinater och koordinater relativt baslinjen.</p><div class="coverage"><b>Befintligt pixel-facit</b>{''.join(coverage) if coverage else '<div>Ingen atlas laddad.</div>'}</div><div class="toolbar"><input id="q" placeholder="Filtrera"><button id="export">Exportera</button><span id="global"></span></div>{''.join(cards)}
<script>
const SCALE={scale},REFS={refs_json};const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];const states=new Map();
function colorFor(l){{let h=0;for(const c of l)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length]}}function key(x,y){{return x+','+y}}function rec(points,baseline){{let xmin=Math.min(...points.map(p=>p[0])),ymin=Math.min(...points.map(p=>p[1]));return {{shape:points.map(([x,y])=>[x-xmin,y-ymin]).sort((a,b)=>a[1]-b[1]||a[0]-b[0]),baseline_offset:baseline-ymin}}}}function sk(s){{return s.map(p=>p[0]+','+p[1]).join(';')}}function diff(a,b){{let A=new Set(a.map(p=>p[0]+','+p[1])),B=new Set(b.map(p=>p[0]+','+p[1])),n=0;for(const x of A)if(!B.has(x))n++;for(const x of B)if(!A.has(x))n++;return n}}
function compare(card,s){{let by={{}};for(const [k,l] of s.pixels)(by[l]??=[]).push(k.split(',').map(Number));let lines=[];for(const l of Object.keys(by).sort()){{let r=rec(by[l],s.baseline),rs=(((REFS[card.dataset.style]||{{}})[l])||[]);if(!rs.length){{lines.push('<b>'+l+'</b>: inget tidigare facit');continue}}let exact=rs.filter(x=>sk(x.shape)===sk(r.shape));if(exact.length){{let offs=[...new Set(exact.map(x=>x.baseline_offset))].sort((a,b)=>a-b);let base=offs.includes(r.baseline_offset)?' · baseline stämmer':' · <span class="basewarn">form identisk; baseline-offset '+r.baseline_offset+' vs '+offs.join('/')+'</span>';lines.push('<span class="exact"><b>'+l+'</b>: PIXELIDENTISK med '+exact.length+' tidigare</span>'+base)}}else{{let best=Math.min(...rs.map(x=>diff(r.shape,x.shape)));lines.push('<span class="near"><b>'+l+'</b>: form ej identisk · närmast '+best+' pixel-diff</span>')}}}}card.querySelector('.comparison').innerHTML=lines.join('<br>')}}
function setup(card){{let cv=card.querySelector('canvas'),ctx=cv.getContext('2d'),img=card.querySelector('.src'),W=+card.dataset.w,H=+card.dataset.h;let raw=document.createElement('canvas');raw.width=W;raw.height=H;let rctx=raw.getContext('2d',{{willReadFrequently:true}});let s={{pixels:new Map(),baseline:+card.dataset.baseline,mode:'box',erase:false,drag:false,start:null,current:null,last:null}};states.set(card,s);
function render(){{ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,cv.width,cv.height);ctx.drawImage(img,0,0,W*SCALE,H*SCALE);ctx.strokeStyle='rgba(100,100,100,.2)';ctx.lineWidth=1;for(let x=0;x<=W;x++){{ctx.beginPath();ctx.moveTo(x*SCALE+.5,0);ctx.lineTo(x*SCALE+.5,H*SCALE);ctx.stroke()}}for(let y=0;y<=H;y++){{ctx.beginPath();ctx.moveTo(0,y*SCALE+.5);ctx.lineTo(W*SCALE,y*SCALE+.5);ctx.stroke()}}for(const [k,l] of s.pixels){{let [x,y]=k.split(',').map(Number);ctx.fillStyle=colorFor(l)+'aa';ctx.fillRect(x*SCALE,y*SCALE,SCALE,SCALE)}}if(s.mode==='box'&&s.drag&&s.start&&s.current){{let x0=Math.min(s.start[0],s.current[0]),y0=Math.min(s.start[1],s.current[1]),x1=Math.max(s.start[0],s.current[0]),y1=Math.max(s.start[1],s.current[1]);ctx.strokeStyle='#1479ff';ctx.lineWidth=3;ctx.strokeRect(x0*SCALE,y0*SCALE,(x1-x0+1)*SCALE,(y1-y0+1)*SCALE)}}ctx.strokeStyle='#e00000';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,(s.baseline+1)*SCALE);ctx.lineTo(W*SCALE,(s.baseline+1)*SCALE);ctx.stroke();card.querySelector('.count').textContent=s.pixels.size+' pixlar';let ls=[...new Set(s.pixels.values())].sort();card.querySelector('.legend').innerHTML=ls.map(l=>'<span class="swatch" style="background:'+colorFor(l)+'">'+l+'</span>').join('');compare(card,s);global()}}
function pos(e){{let rr=cv.getBoundingClientRect();return [Math.max(0,Math.min(W-1,Math.floor((e.clientX-rr.left)/SCALE))),Math.max(0,Math.min(H-1,Math.floor((e.clientY-rr.top)/SCALE)))]}}function inkAt(x,y){{let d=rctx.getImageData(x,y,1,1).data,gray=.299*d[0]+.587*d[1]+.114*d[2];return gray < +card.querySelector('.threshold').value}}function pixelPaint(e){{let [x,y]=pos(e),k=key(x,y);if(s.last===k&&s.drag)return;s.last=k;if(s.erase||e.altKey)s.pixels.delete(k);else{{let l=card.querySelector('.label').value.trim();if(!l)return;let old=s.pixels.get(k);if(!s.drag&&old===l)s.pixels.delete(k);else s.pixels.set(k,l)}}render()}}function commitBox(){{if(!s.start||!s.current)return;let l=card.querySelector('.label').value.trim();if(!l)return;let x0=Math.min(s.start[0],s.current[0]),y0=Math.min(s.start[1],s.current[1]),x1=Math.max(s.start[0],s.current[0]),y1=Math.max(s.start[1],s.current[1]);for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)if(inkAt(x,y))s.pixels.set(key(x,y),l)}}
cv.onpointerdown=e=>{{cv.setPointerCapture(e.pointerId);s.drag=true;s.last=null;if(s.mode==='box'){{s.start=pos(e);s.current=s.start;render()}}else pixelPaint(e)}};cv.onpointermove=e=>{{if(!s.drag)return;if(s.mode==='box'){{s.current=pos(e);render()}}else pixelPaint(e)}};cv.onpointerup=()=>{{if(s.mode==='box')commitBox();s.drag=false;s.start=s.current=null;s.last=null;render()}};card.querySelector('.boxmode').onclick=()=>{{s.mode='box';card.querySelector('.boxmode').classList.add('active');card.querySelector('.pixelmode').classList.remove('active')}};card.querySelector('.pixelmode').onclick=()=>{{s.mode='pixel';card.querySelector('.pixelmode').classList.add('active');card.querySelector('.boxmode').classList.remove('active')}};let b=card.querySelector('.baseline');b.onchange=()=>{{s.baseline=Math.max(0,Math.min(H-1,+b.value));b.value=s.baseline;render()}};card.querySelector('.up').onclick=()=>{{b.value=Math.max(0,s.baseline-1);b.onchange()}};card.querySelector('.down').onclick=()=>{{b.value=Math.min(H-1,s.baseline+1);b.onchange()}};let er=card.querySelector('.erase');er.onclick=()=>{{s.erase=!s.erase;er.textContent='Sudd: '+(s.erase?'på':'av')}};card.querySelector('.clear').onclick=()=>{{if(confirm('Rensa ordet?')){{s.pixels.clear();render()}}}};function ready(){{rctx.drawImage(img,0,0,W,H);render()}}if(img.complete)ready();else img.onload=ready}}
function global(){{let p=0,w=0;for(const s of states.values()){{p+=s.pixels.size;if(s.pixels.size)w++}}document.querySelector('#global').textContent=w+' ord · '+p+' pixlar'}}document.querySelectorAll('.card').forEach(setup);document.querySelector('#q').oninput=e=>{{let q=e.target.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',!(c.dataset.expected+' '+c.dataset.headword+' '+c.dataset.style+' '+c.dataset.page).toLowerCase().includes(q)))}};
document.querySelector('#export').onclick=()=>{{let words=[];for(const [card,s] of states){{if(!s.pixels.size)continue;let by={{}};for(const [k,l] of s.pixels)(by[l]??=[]).push(k.split(',').map(Number));let annotations=Object.entries(by).map(([label,pixels])=>{{pixels.sort((a,b)=>a[1]-b[1]||a[0]-b[0]);let rr=rec(pixels,s.baseline);return {{label,pixels,pixels_relative_to_baseline:pixels.map(([x,y])=>[x,y-s.baseline]),shape:rr.shape,baseline_offset:rr.baseline_offset}}}});words.push({{source_id:card.dataset.sourceId,expected_word:card.dataset.expected,headword:card.dataset.headword,style:card.dataset.style,page:Number(card.dataset.page),subnr:card.dataset.subnr,word_file:card.dataset.wordFile,width:+card.dataset.w,height:+card.dataset.h,baseline_y:s.baseline,baseline_auto_y:+card.dataset.baseline,baseline_auto_confidence:+card.dataset.baselineConfidence,annotations}})}}let out={{format:'saol-manual-pixel-atlas-v3',coordinate_system:'word crop origin top-left; y_rel = y - baseline_y',words}};let blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-pixel-atlas-v3.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(words)} scale={scale} threshold={args.ink_threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
