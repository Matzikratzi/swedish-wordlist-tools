from __future__ import annotations

import argparse
import base64
import html
import json
from collections import Counter
from pathlib import Path


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _manifest(library: Path) -> tuple[Path, dict]:
    for name in ("manifest-style-word-segments.json", "manifest-word-segments.json"):
        p = library / name
        if p.exists():
            return p, json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit(f"missing word manifest in {library}")


def _rank_words(words: list[dict], limit: int) -> list[dict]:
    # Greedy coverage: first seek unseen characters, then underrepresented characters.
    remaining = list(words)
    chosen: list[dict] = []
    counts: Counter[str] = Counter()
    while remaining and (limit <= 0 or len(chosen) < limit):
        def score(w: dict) -> tuple[float, int, int]:
            text = str(w.get("expected_word") or "")
            chars = set(text)
            novelty = sum(8.0 if counts[c] == 0 else 2.0 / (1 + counts[c]) for c in chars)
            rare = sum(1.0 / (1 + counts[c]) for c in text)
            return novelty + rare, len(chars), len(text)
        best = max(remaining, key=score)
        remaining.remove(best)
        chosen.append(best)
        counts.update(str(best.get("expected_word") or ""))
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a manual glyph/cluster atlas review page with freehand bounding boxes.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--style", choices=("roman", "italic"))
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--scale", type=int, default=8)
    args = ap.parse_args()

    manifest_path, payload = _manifest(args.library)
    words = [w for w in payload.get("words", []) if isinstance(w, dict) and isinstance(w.get("word_file"), str)]
    if args.style:
        words = [w for w in words if w.get("style") == args.style]
    words = [w for w in words if (args.library / str(w["word_file"])).exists()]
    words = _rank_words(words, args.limit)

    cards = []
    for n, w in enumerate(words):
        rel = str(w["word_file"])
        text = str(w.get("expected_word") or "")
        headword = str(w.get("headword") or "")
        style = str(w.get("style") or "")
        meta = f"sida {w.get('page','')} · subnr {w.get('subnr','')} · {style}"
        cards.append(f'''<article class="card" data-i="{n}" data-source="{html.escape(str(w.get('source_id','')), quote=True)}" data-word="{html.escape(text, quote=True)}" data-headword="{html.escape(headword, quote=True)}" data-style="{html.escape(style, quote=True)}" data-file="{html.escape(rel, quote=True)}">
<header><strong>{html.escape(text)}</strong><span class="headword">uppslagsord: <b>{html.escape(headword or 'saknas i äldre manifest')}</b></span><span>{html.escape(meta)}</span></header>
<div class="hint">Dra en box runt en klockren glyph eller ett sammanhängande kluster. Skriv etiketten och tryck Enter. Hoppa över allt tveksamt.</div>
<div class="stage" style="--s:{max(1,args.scale)}"><img src="{_data_uri(args.library / rel)}"><canvas></canvas></div>
<div class="entry"><label>Etikett <input class="label" placeholder="t.ex. a, i, st, äm"></label><button class="add" disabled>Lägg till box</button><button class="undo">Ångra senaste</button></div>
<div class="boxes"></div>
</article>''')

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL manual glyph atlas</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:22px;background:#f3f3f3;color:#171717}}h1{{margin-bottom:.25rem}}.intro{{max-width:1000px;color:#444}}.toolbar{{position:sticky;top:0;background:#f3f3f3ee;padding:10px 0;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}input,button{{font:inherit;padding:.4rem .55rem}}#q{{width:26rem;max-width:100%}}.card{{background:#fff;border:1px solid #bbb;border-radius:9px;padding:14px;margin:14px 0}}header{{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}}header strong{{font-size:24px}}.headword{{background:#eef;padding:3px 7px;border-radius:5px}}.hint{{font-size:12px;color:#666;margin:8px 0}}.stage{{position:relative;display:inline-block;background:#eee;border:1px solid #888;margin:8px 0;line-height:0;overflow:visible}}.stage img{{display:block;image-rendering:pixelated;transform:scale(var(--s));transform-origin:top left}}.stage{{margin-right:calc((var(--s) - 1) * 100px);margin-bottom:80px}}canvas{{position:absolute;left:0;top:0;z-index:2;cursor:crosshair;image-rendering:pixelated}}.entry{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}.label{{width:12rem}}.boxes{{font-size:13px;margin-top:8px}}.tag{{display:inline-block;background:#e8f4e8;border:1px solid #9b9;padding:3px 7px;border-radius:999px;margin:3px}}.hidden{{display:none}}#stats{{color:#555}}
</style>
<h1>Manuell glyph-atlas</h1><p class="intro">{len(words)} textsträngar valda för bred teckentäckning. Boxarna är facit: välj bara former du själv tycker är klockrena. Du får boxa en bokstav eller ett återkommande kluster. Inget automatiskt segmenteringsresultat används.</p>
<div class="toolbar"><input id="q" placeholder="Filtrera på text, uppslagsord eller stil…"><button id="export">Exportera atlas-feedback</button><span id="stats"></span></div>
{''.join(cards)}
<script>
const SCALE={max(1,args.scale)}; const state={{}};
function setup(card){{
 const i=card.dataset.i,img=card.querySelector('img'),cv=card.querySelector('canvas'),ctx=cv.getContext('2d'),inp=card.querySelector('.label'),add=card.querySelector('.add'),list=card.querySelector('.boxes'); state[i]=[]; let start=null,current=null;
 function size(){{cv.width=img.naturalWidth*SCALE;cv.height=img.naturalHeight*SCALE;cv.style.width=cv.width+'px';cv.style.height=cv.height+'px';card.querySelector('.stage').style.width=cv.width+'px';card.querySelector('.stage').style.height=cv.height+'px';img.style.transform='scale('+SCALE+')';draw();}}
 function draw(){{ctx.clearRect(0,0,cv.width,cv.height);ctx.lineWidth=2;ctx.strokeStyle='red';for(const b of state[i])ctx.strokeRect(b.x*SCALE,b.y*SCALE,b.w*SCALE,b.h*SCALE);if(current){{ctx.strokeStyle='blue';ctx.strokeRect(current.x*SCALE,current.y*SCALE,current.w*SCALE,current.h*SCALE)}};list.innerHTML=state[i].map(b=>'<span class="tag">'+esc(b.label)+' ['+[b.x,b.y,b.w,b.h].join(', ')+']</span>').join('');stats();}}
 function pos(e){{const r=cv.getBoundingClientRect();return {{x:Math.max(0,Math.min(img.naturalWidth,Math.round((e.clientX-r.left)/SCALE))),y:Math.max(0,Math.min(img.naturalHeight,Math.round((e.clientY-r.top)/SCALE)))}}}}
 cv.onpointerdown=e=>{{cv.setPointerCapture(e.pointerId);start=pos(e);current={{x:start.x,y:start.y,w:0,h:0}};draw()}};
 cv.onpointermove=e=>{{if(!start)return;const p=pos(e);current={{x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y)}};draw()}};
 cv.onpointerup=e=>{{if(!start)return;const p=pos(e);current={{x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(p.x-start.x),h:Math.abs(p.y-start.y)}};start=null;add.disabled=!(current.w&&current.h&&inp.value.trim());inp.focus();draw()}};
 inp.oninput=()=>add.disabled=!(current&&current.w&&current.h&&inp.value.trim());inp.onkeydown=e=>{{if(e.key==='Enter'&&!add.disabled){{e.preventDefault();add.click()}}}};
 add.onclick=()=>{{if(!current||!inp.value.trim())return;state[i].push({{...current,label:inp.value.trim()}});current=null;inp.value='';add.disabled=true;draw()}};
 card.querySelector('.undo').onclick=()=>{{state[i].pop();draw()}}; if(img.complete)size();else img.onload=size;
}}
function esc(s){{return s.replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function stats(){{const n=Object.values(state).reduce((a,x)=>a+x.length,0);document.getElementById('stats').textContent=n+' boxar'}}
document.querySelectorAll('.card').forEach(setup);
document.getElementById('q').oninput=e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('.card').forEach(c=>c.classList.toggle('hidden',!(c.dataset.word+' '+c.dataset.headword+' '+c.dataset.style).toLowerCase().includes(q)))}};
document.getElementById('export').onclick=()=>{{const annotations=[];document.querySelectorAll('.card').forEach(c=>{{for(const b of state[c.dataset.i])annotations.push({{source_id:c.dataset.source,expected_word:c.dataset.word,headword:c.dataset.headword,style:c.dataset.style,word_file:c.dataset.file,label:b.label,bbox:[b.x,b.y,b.w,b.h]}})}});const out={{format:'saol-manual-glyph-atlas-v1',manifest:{json.dumps(manifest_path.name)},annotations}};const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-manual-glyph-atlas.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}};
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(words)} style={args.style or 'both'} manifest={manifest_path.name}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
