from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description="Review topology-filtered manual pixel matches in HTML.")
    ap.add_argument("matches", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=18)
    args = ap.parse_args()

    payload = json.loads(args.matches.read_text(encoding="utf-8"))
    cards: list[str] = []
    scale = max(4, args.scale)

    for i, word in enumerate(payload.get("results", [])):
        if not isinstance(word, dict):
            continue
        rel = str(word.get("word_file") or "")
        path = args.library / rel
        if not rel or not path.exists():
            continue
        matches = word.get("matches") or {}
        overlays: list[dict[str, object]] = []
        for label, hits in matches.items():
            for hit in hits:
                overlays.append(
                    {
                        "label": label,
                        "pixels": hit.get("matched_pixels", []),
                        "contacts": hit.get("external_contact_pixels", []),
                        "missing": hit.get("missing", 0),
                        "extra": hit.get("extra", 0),
                        "external_contacts": hit.get("external_contacts", 0),
                        "baseline_dy": hit.get("baseline_dy", 0),
                    }
                )
        cards.append(
            f'''<article class="card" data-overlay='{html.escape(json.dumps(overlays, ensure_ascii=False), quote=True)}'>
<header><strong>{html.escape(str(word.get("expected_word") or ""))}</strong>
<span class="badge">{html.escape(str(word.get("style") or ""))}</span>
<span>uppslagsord: <b>{html.escape(str(word.get("headword") or "")) or "(saknas)"}</b></span>
<span>sida {html.escape(str(word.get("page") or ""))} · subnr {html.escape(str(word.get("subnr") or ""))}</span>
</header>
<div class="canvaswrap"><canvas width="{int(word.get('width') or 0)*scale}" height="{int(word.get('height') or 0)*scale}"></canvas></div>
<img class="src" src="{_data_uri(path)}" hidden>
<div class="legend"></div>
</article>'''
        )

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL pixelmatch review</title>
<style>
*{{box-sizing:border-box}}body{{font-family:system-ui;margin:20px;background:#f3f3f3;color:#171717}}
.card{{background:#fff;border:1px solid #bbb;border-radius:8px;padding:10px;margin:12px 0}}
header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:2px 7px}}
.canvaswrap{{display:inline-block;overflow:auto;max-width:100%;border:1px solid #999;background:#ddd}}canvas{{display:block;image-rendering:pixelated}}
.legend{{margin-top:6px;font-size:13px;line-height:1.5}}.ok{{color:#08752b;font-weight:700}}.bad{{color:#a33;font-weight:700}}
</style>
<h1>SAOL pixelmatch review</h1>
<p>Färgade rutor är de pixlar som matchern faktiskt använder. Röda rutor skulle vara externa 8-grannkontakter; med standardfiltret ska de inte förekomma alls.</p>
{''.join(cards)}
<script>
const SCALE={scale}; const palette=['#1479ff','#e83e8c','#16a34a','#f59e0b','#7c3aed','#0891b2','#dc2626','#4f46e5','#65a30d','#c2410c'];
function colorFor(l){{let h=0;for(const c of l)h=(h*33+c.codePointAt(0))>>>0;return palette[h%palette.length]}}
document.querySelectorAll('.card').forEach(card=>{{
 const cv=card.querySelector('canvas'),ctx=cv.getContext('2d'),img=card.querySelector('.src'),ovs=JSON.parse(card.dataset.overlay);
 function draw(){{ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,cv.width,cv.height);ctx.drawImage(img,0,0,cv.width,cv.height);let lines=[];for(const o of ovs){{ctx.fillStyle=colorFor(o.label)+'99';for(const p of o.pixels)ctx.fillRect(p[0]*SCALE,p[1]*SCALE,SCALE,SCALE);ctx.fillStyle='#ff0000aa';for(const p of o.contacts)ctx.fillRect(p[0]*SCALE,p[1]*SCALE,SCALE,SCALE);let cls=o.external_contacts===0?'ok':'bad';lines.push('<span class="'+cls+'">'+o.label+'</span>: missing='+o.missing+' extra='+o.extra+' contacts='+o.external_contacts+' dy='+o.baseline_dy)}}card.querySelector('.legend').innerHTML=lines.join('<br>')}}
 if(img.complete)draw();else img.onload=draw;
}})
</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"cards={len(cards)} scale={scale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
