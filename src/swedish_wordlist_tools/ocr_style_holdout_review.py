from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _h(x: object) -> str:
    return html.escape(str(x), quote=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Visual QC page for mixed-style holdout results.")
    ap.add_argument("holdout", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--errors-only", action="store_true")
    args = ap.parse_args()

    bench = json.loads(args.holdout.read_text(encoding="utf-8"))
    manifest_path = args.library / "manifest-style-word-segments.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_source = {int(w["source_id"]): w for w in manifest.get("words", []) if isinstance(w, dict) and "source_id" in w}

    cards: list[str] = []
    missing = 0
    for r in bench.get("results", []):
        if not isinstance(r, dict):
            continue
        if args.errors_only and r.get("correct") is True:
            continue
        sid = int(r.get("source_id", -1))
        word = by_source.get(sid)
        if not isinstance(word, dict):
            missing += 1
            continue
        wr = word.get("word_file")
        if not isinstance(wr, str) or not (args.library / wr).exists():
            missing += 1
            continue
        src_segments = [s for s in word.get("segments", []) if isinstance(s, dict)]
        result_segments = [s for s in r.get("segments", []) if isinstance(s, dict)]
        units: list[str] = []
        for i, rr in enumerate(result_segments):
            src = src_segments[i] if i < len(src_segments) else {}
            rel = src.get("file")
            if isinstance(rel, str) and (args.library / rel).exists():
                pic = f'<img src="{_data_uri(args.library / rel)}" alt="segment">'
            else:
                pic = '<span>saknar bild</span>'
                missing += 1
            truth = str(rr.get("expected") or src.get("expected_text") or src.get("character") or "")
            pred = rr.get("prediction")
            raw = rr.get("raw_prediction")
            status = rr.get("status")
            if status == "missing-class-after-holdout" or raw is None:
                css, verdict = "uneval", "EJ TESTBAR"
            elif pred == truth:
                css, verdict = "right", "RÄTT"
            elif raw == truth and pred == "?":
                css, verdict = "margin", "RÄTT RAW, STOPPAD"
            else:
                css, verdict = "wrong", "FELKLASSAD"
            units.append(
                f'<figure class="unit {css}" data-i="{i}" data-truth="{_h(truth)}">'
                f'<div class="frame">{pic}</div><figcaption><b>{_h(truth)}</b> · {_h(rr.get("kind", ""))}</figcaption>'
                f'<div class="verdict">{verdict}</div><div class="meta">pred={_h(pred)} raw={_h(raw)}<br>margin={_h(rr.get("margin"))} sources={_h(rr.get("independent_sources"))}</div>'
                '<select class="unit-status"><option value="ok" selected>visuellt OK</option><option value="bad-segment">fel crop/segment</option><option value="missing-mark">saknar prick/diakrit</option><option value="should-cluster">borde vara kluster</option><option value="wrong-truth">fel facit</option><option value="other">annat</option></select>'
                '</figure>'
            )
        expected = str(r.get("expected") or word.get("expected_word") or "")
        prediction = str(r.get("prediction") or "")
        style = str(r.get("style") or word.get("style") or "")
        headword = str(word.get("headword") or "")
        searchable = f"{style} {expected} {headword} {r.get('page')} {r.get('subnr')} {sid}".lower()
        headword_html = f'<span class="headword">uppslagsord: <b>{_h(headword)}</b></span>' if headword else '<span class="headword missinghw">uppslagsord saknas i detta äldre manifest</span>'
        cards.append(
            f'<article class="word {"okword" if r.get("correct") else "badword"}" data-source-id="{sid}" data-search="{_h(searchable)}">'
            f'<header><strong>{_h(expected)}</strong><span>→</span><strong>{_h(prediction)}</strong><span class="badge">{_h(style)}</span>{headword_html}<span>source {sid}</span><span>sida {_h(r.get("page"))}</span></header>'
            f'<div class="whole"><div class="wordframe"><img src="{_data_uri(args.library / wr)}" alt="{_h(expected)}"></div>'
            '<select class="word-status"><option value="ok" selected>ordcrop OK</option><option value="bad-word-crop">fel ordcrop</option><option value="wrong-word">fel facitord</option><option value="wrong-style">fel stil</option><option value="other">annat</option></select><input class="note" placeholder="Kommentar"></div>'
            '<div class="units">' + ''.join(units) + '</div></article>'
        )

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL holdout QC</title>
<style>:root{{--scale:{max(1,args.scale)}}}*{{box-sizing:border-box}}body{{font-family:system-ui;margin:24px;background:#f4f4f4;color:#171717}}.toolbar{{position:sticky;top:0;background:#f4f4f4ee;padding:10px 0;z-index:5;display:flex;gap:10px;flex-wrap:wrap}}input,select,button{{font:inherit}}#q{{width:28rem;padding:.45rem}}.word{{background:#fff;border:1px solid #bbb;border-radius:9px;margin:15px 0;padding:14px}}.badword{{border-left:5px solid #a22}}.okword{{border-left:5px solid #287a35}}header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}header strong{{font-size:22px}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:3px 7px;text-transform:uppercase}}.headword{{padding:.28rem .5rem;background:#eef3ff;border:1px solid #aab9db;border-radius:5px}}.headword b{{font-size:16px}}.missinghw{{color:#777;background:#eee;border-color:#ccc}}.whole{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}}.note{{min-width:280px;flex:1;padding:.35rem}}.wordframe,.frame{{background:#eee;border:1px solid #999;display:flex;align-items:center;justify-content:center;overflow:hidden}}.wordframe{{width:300px;height:90px}}.frame{{width:100px;height:82px}}img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}.units{{display:flex;gap:9px;flex-wrap:wrap;align-items:flex-start}}.unit{{width:112px;margin:0;padding:5px;border-radius:6px;text-align:center}}.right{{background:#e8f6e9}}.wrong{{background:#ffe3e3;border:1px solid #d77}}.margin{{background:#fff4c8;border:1px solid #d2b34f}}.uneval{{background:#e7e7e7;border:1px dashed #888}}figcaption{{font-size:19px;margin-top:4px}}.verdict{{font-size:10px;font-weight:800;margin:3px 0}}.meta{{font-size:10px;color:#555;min-height:30px}}.unit select{{width:102px;font-size:10px}}.hidden{{display:none}}#summary{{font-size:13px;color:#555}}</style>
<h1>SAOL holdout QC</h1><p>Varje granskat ord visar också vilket SAOL-uppslagsord det hör till när manifestet innehåller den informationen. Granska att exakt samma synliga word-crop innehåller allt som segmenten på raden påstår sig innehålla. {len(cards)} ord, saknade bilder: {missing}.</p>
<div class="toolbar"><input id="q" placeholder="Filtrera ord/uppslagsord/stil/sida/source"><button id="issues">Visa bara markeringar</button><button id="export">Exportera feedback</button><span id="summary"></span></div>{''.join(cards)}
<script>const q=document.querySelector('#q'),sum=document.querySelector('#summary');let only=false;function issue(w){{return w.querySelector('.word-status').value!=='ok'||[...w.querySelectorAll('.unit-status')].some(s=>s.value!=='ok')}}function refresh(){{let n=0;document.querySelectorAll('.word').forEach(w=>{{let bad=issue(w);if(bad)n++;let show=w.dataset.search.includes(q.value.toLowerCase())&&(!only||bad);w.classList.toggle('hidden',!show)}});sum.textContent=n+' ord markerade'}}q.oninput=refresh;document.querySelectorAll('select').forEach(s=>s.onchange=refresh);document.querySelector('#issues').onclick=()=>{{only=!only;refresh()}};document.querySelector('#export').onclick=()=>{{let words=[...document.querySelectorAll('.word')].map(w=>({{source_id:Number(w.dataset.sourceId),word_status:w.querySelector('.word-status').value,note:w.querySelector('.note').value,units:[...w.querySelectorAll('.unit')].map(u=>({{index:Number(u.dataset.i),truth:u.dataset.truth,status:u.querySelector('.unit-status').value}}))}}));let b=new Blob([JSON.stringify({{format:'saol-holdout-review-v1',words}},null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='saol14-holdout-review-feedback.json';a.click()}};refresh();</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(cards)} missing={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
