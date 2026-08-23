from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _h(x: object) -> str:
    return html.escape(str(x), quote=True)


def _uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _headwords(jsonl: Path | None) -> dict[object, str]:
    out: dict[object, str] = {}
    if jsonl is None or not jsonl.exists():
        return out
    with jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            sub = row.get("subnr")
            text = row.get("lemma") or row.get("headword") or row.get("uppslagsord") or row.get("ord")
            if not isinstance(text, str):
                raw = row.get("text")
                if isinstance(raw, str):
                    text = raw.split(None, 1)[0] if raw.strip() else ""
            if sub is not None and isinstance(text, str) and text:
                out[sub] = text
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Visual QC for high-confidence trusted-library expansion candidates.")
    ap.add_argument("candidates", type=Path)
    ap.add_argument("library", type=Path)
    ap.add_argument("--jsonl", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=6)
    args = ap.parse_args()

    payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    heads = _headwords(args.jsonl)
    cards = []
    for n, c in enumerate(payload.get("candidates", [])):
        if not isinstance(c, dict):
            continue
        wr, sr = c.get("word_file"), c.get("segment_file")
        if not isinstance(wr, str) or not isinstance(sr, str):
            continue
        wp, sp = args.library / wr, args.library / sr
        if not wp.exists() or not sp.exists():
            continue
        head = c.get("headword") or heads.get(c.get("subnr")) or "(uppslagsord saknas)"
        truth = str(c.get("truth") or "")
        search = f"{head} {c.get('expected_word')} {truth} {c.get('style')} {c.get('kind')} {c.get('page')} {c.get('source_id')}".lower()
        cards.append(f'''<article class="card" data-n="{n}" data-search="{_h(search)}">
<header><b>uppslagsord: {_h(head)}</b> <span class="badge">{_h(c.get('style'))}</span> sida {_h(c.get('page'))} · source {_h(c.get('source_id'))}</header>
<div class="meta">granskat ord: <b>{_h(c.get('expected_word'))}</b> · enhet: <b>{_h(truth)}</b> ({_h(c.get('kind'))}) · score={_h(c.get('score'))} · margin={_h(c.get('margin'))}</div>
<div class="pics"><figure><figcaption>EXAKT WORD-CROP</figcaption><div class="wordframe"><img src="{_uri(wp)}"></div></figure><figure><figcaption>EXAKT KLASSIFICERAD ENHET</figcaption><div class="unitframe"><img src="{_uri(sp)}"></div></figure></div>
<div><select class="status"><option value="ok" selected>klockren — lägg till</option><option value="bad-word-crop">fel word-crop</option><option value="bad-unit">fel segment/enhet</option><option value="wrong-truth">fel facit</option><option value="other">annat</option></select> <input class="note" placeholder="Kommentar"></div>
</article>''')

    doc = f'''<!doctype html><meta charset="utf-8"><title>SAOL trusted candidates</title><style>:root{{--scale:{max(1,args.scale)}}}*{{box-sizing:border-box}}body{{font-family:system-ui;margin:24px;background:#f4f4f4}}.toolbar{{position:sticky;top:0;background:#f4f4f4ee;padding:10px 0;z-index:5}}#q{{width:32rem;padding:.45rem}}.card{{background:white;border:1px solid #bbb;border-left:5px solid #287a35;border-radius:8px;padding:13px;margin:13px 0}}header{{display:flex;gap:12px;align-items:center;flex-wrap:wrap}}.badge{{font-size:11px;border:1px solid #888;border-radius:999px;padding:3px 7px;text-transform:uppercase}}.meta{{margin:8px 0;color:#444}}.pics{{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap}}figure{{margin:4px 0}}figcaption{{font-size:10px;font-weight:800}}.wordframe,.unitframe{{background:#eee;border:1px solid #999;display:flex;align-items:center;justify-content:center;overflow:hidden}}.wordframe{{width:360px;height:100px}}.unitframe{{width:130px;height:100px}}img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}select,input{{font:inherit}}.note{{width:26rem;padding:.3rem}}.hidden{{display:none}}</style>
<h1>Trusted candidate review</h1><p>Det som visas som <b>EXAKT WORD-CROP</b> och <b>EXAKT KLASSIFICERAD ENHET</b> är de filer som candidate-minern använde. Godkänn bara när båda är visuellt klockrena.</p><div class="toolbar"><input id="q" placeholder="Filtrera uppslagsord/ord/tecken/stil/sida"> <button id="issues">Visa bara avvisade</button> <button id="export">Exportera feedback</button> <span id="sum"></span></div>{''.join(cards)}
<script>const q=document.querySelector('#q');let only=false;function refresh(){{let bad=0;document.querySelectorAll('.card').forEach(c=>{{const issue=c.querySelector('.status').value!=='ok';if(issue)bad++;c.classList.toggle('hidden',!c.dataset.search.includes(q.value.toLowerCase())||(only&&!issue))}});document.querySelector('#sum').textContent=bad+' avvisade'}}q.oninput=refresh;document.querySelectorAll('select').forEach(s=>s.onchange=refresh);document.querySelector('#issues').onclick=()=>{{only=!only;refresh()}};document.querySelector('#export').onclick=()=>{{const candidates=[...document.querySelectorAll('.card')].map(c=>({{candidate_index:Number(c.dataset.n),status:c.querySelector('.status').value,note:c.querySelector('.note').value}}));const b=new Blob([JSON.stringify({{format:'saol-trusted-candidate-review-v1',candidates}},null,2)+'\\n'],{{type:'application/json'}}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='saol14-trusted-candidate-feedback.json';a.click()}};refresh();</script>'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"candidates={len(cards)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
