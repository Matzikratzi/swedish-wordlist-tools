from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _load_sources(jsonl: Path | None) -> dict[str, str]:
    if jsonl is None:
        return {}
    out: dict[str, str] = {}
    with jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            subnr = row.get("subnr")
            source = row.get("source")
            if subnr is not None and isinstance(source, str) and source:
                out[str(subnr)] = source
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a static visual QC page for whole-word segmented roman/italic glyphs.")
    ap.add_argument("library", type=Path)
    ap.add_argument("--jsonl", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--style", choices=("roman", "italic"))
    args = ap.parse_args()

    candidates = [args.library / "manifest-style-word-segments.json", args.library / "manifest-word-segments.json"]
    manifest_path = next((p for p in candidates if p.exists()), None)
    if manifest_path is None:
        raise SystemExit("missing word-segment manifest; tried: " + ", ".join(str(p) for p in candidates))
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = _load_sources(args.jsonl)

    words = [w for w in payload.get("words", []) if isinstance(w, dict)]
    if args.style:
        words = [w for w in words if w.get("style") == args.style]

    cards: list[str] = []
    missing = 0
    for row in words:
        source_id = row.get("source_id", "")
        style = str(row.get("style") or "")
        expected = str(row.get("expected_word") or "")
        page = row.get("page", "")
        subnr = row.get("subnr", "")
        word_rel = row.get("word_file")
        if not isinstance(word_rel, str):
            missing += 1
            continue
        word_path = args.library / word_rel
        if not word_path.exists():
            missing += 1
            continue

        glyph_html: list[str] = []
        for g in row.get("glyphs", []):
            if not isinstance(g, dict):
                continue
            ch = str(g.get("character") or "")
            idx = g.get("index", "")
            rel = g.get("file")
            if not isinstance(rel, str):
                continue
            path = args.library / rel
            if not path.exists():
                missing += 1
                continue
            glyph_html.append(
                f'<figure class="glyph" data-index="{html.escape(str(idx), quote=True)}" data-char="{html.escape(ch, quote=True)}" data-file="{html.escape(rel, quote=True)}">'
                f'<div class="gframe"><img src="{_data_uri(path)}" alt="{html.escape(ch)}"></div>'
                f'<figcaption>{html.escape(ch)}</figcaption>'
                '<select class="glyph-status">'
                '<option value="ok" selected>OK</option>'
                '<option value="wrong-segment">fel segment</option>'
                '<option value="missing-part">saknar del</option>'
                '<option value="has-neighbor">har grannbokstav</option>'
                '<option value="wrong-character">fel bokstav</option>'
                '<option value="other">annat</option>'
                '</select>'
                '</figure>'
            )

        source = sources.get(str(subnr))
        source_html = (
            f'<a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">faksimil sida {html.escape(str(page))} ↗</a>'
            if source else f'<span>sida {html.escape(str(page))}</span>'
        )
        searchable = f"{style} {expected} {page} {subnr}".lower()
        cards.append(
            f'<article class="word" data-search="{html.escape(searchable, quote=True)}" data-source-id="{html.escape(str(source_id), quote=True)}" data-style="{html.escape(style, quote=True)}" data-expected="{html.escape(expected, quote=True)}" data-page="{html.escape(str(page), quote=True)}" data-subnr="{html.escape(str(subnr), quote=True)}" data-word-file="{html.escape(word_rel, quote=True)}">'
            '<header>'
            f'<strong>{html.escape(expected)}</strong><span class="badge">{html.escape(style)}</span><span>subnr {html.escape(str(subnr))}</span>{source_html}'
            '</header>'
            '<div class="word-feedback"><span>Hela ordet:</span><select class="word-status">'
            '<option value="ok" selected>OK</option><option value="bad-crop">fel crop</option><option value="wrong-word">fel ord</option><option value="wrong-style">fel stil</option><option value="other">annat</option>'
            '</select><input class="note" placeholder="Kommentar (valfritt)"></div>'
            '<div class="comparison"><div class="whole"><div class="label">hela ordet</div>'
            f'<div class="wframe"><img src="{_data_uri(word_path)}" alt="{html.escape(expected)}"></div></div>'
            '<div class="segments"><div class="label">segment</div><div class="glyphrow">' + ''.join(glyph_html) + '</div></div></div>'
            '</article>'
        )

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL word-segment QC</title>
<style>
:root{{--scale:{max(1,args.scale)};}}*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;margin:24px;background:#f4f4f4;color:#151515}}h1{{margin-bottom:.3rem}}.intro{{color:#555;max-width:950px}}.toolbar{{position:sticky;top:0;padding:10px 0;background:#f4f4f4ee;z-index:5;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}input,select,button{{font:inherit}}#q{{padding:.5rem .7rem;width:28rem;max-width:100%;border:1px solid #aaa;border-radius:6px}}button{{padding:.5rem .75rem}}.word{{background:white;border:1px solid #ccc;border-radius:9px;padding:14px;margin:14px 0}}.word.issue{{border:2px solid #b33}}.word header{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}}.word header strong{{font-size:22px}}.badge{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;padding:3px 7px;border:1px solid #999;border-radius:999px}}.word-feedback{{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:12px;padding:8px;background:#fafafa;border:1px solid #ddd}}.note{{min-width:320px;flex:1;padding:.35rem .5rem}}.comparison{{display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap}}.label{{font-size:12px;color:#666;margin-bottom:7px}}.wframe,.gframe{{background:#eee;border:1px solid #aaa;display:flex;align-items:center;justify-content:center;overflow:hidden}}.wframe{{min-width:260px;height:100px}}.wframe img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}.glyphrow{{display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}}.glyph{{margin:0;width:96px;text-align:center;padding:5px;border-radius:6px}}.glyph.issue{{background:#fee;border:1px solid #c88}}.gframe{{width:88px;height:76px}}.gframe img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}.glyph figcaption{{font-size:24px;font-weight:700;line-height:1.2;margin-top:4px}}.glyph select{{width:92px;font-size:11px}}.hidden{{display:none}}a{{color:#0645ad}}#summary{{font-size:13px;color:#444}}
</style>
<h1>SAOL word-segment QC</h1>
<p class="intro">{len(cards)} ord. Allt är <b>OK som standard</b>. Markera bara avvikelser på ord- eller glyphnivå, skriv kommentar vid behov och klicka sedan <b>Exportera feedback</b>. Saknade filer: {missing}. Manifest: {html.escape(manifest_path.name)}.</p>
<div class="toolbar"><input id="q" placeholder="Filtrera på ord, stil, sida eller subnr…"><button id="export">Exportera feedback</button><button id="onlyissues">Visa bara fel</button><span id="summary"></span></div>
{''.join(cards)}
<script>
const q=document.getElementById('q'), summary=document.getElementById('summary');let onlyIssues=false;
function isIssue(w){{if(w.querySelector('.word-status').value!=='ok')return true;return [...w.querySelectorAll('.glyph-status')].some(s=>s.value!=='ok');}}
function refresh(){{let issues=0;document.querySelectorAll('.word').forEach(w=>{{const issue=isIssue(w);w.classList.toggle('issue',issue);w.querySelectorAll('.glyph').forEach(g=>g.classList.toggle('issue',g.querySelector('.glyph-status').value!=='ok'));const textok=w.dataset.search.includes(q.value.toLowerCase());w.classList.toggle('hidden',!textok||(onlyIssues&&!issue));if(issue)issues++;}});summary.textContent=issues+' ord med markerad avvikelse';}}
q.addEventListener('input',refresh);document.querySelectorAll('select').forEach(s=>s.addEventListener('change',refresh));
document.getElementById('onlyissues').onclick=()=>{{onlyIssues=!onlyIssues;document.getElementById('onlyissues').textContent=onlyIssues?'Visa alla':'Visa bara fel';refresh();}};
document.getElementById('export').onclick=()=>{{const words=[...document.querySelectorAll('.word')].map(w=>({{source_id:w.dataset.sourceId,style:w.dataset.style,expected_word:w.dataset.expected,page:Number(w.dataset.page),subnr:w.dataset.subnr,word_file:w.dataset.wordFile,word_status:w.querySelector('.word-status').value,note:w.querySelector('.note').value,glyphs:[...w.querySelectorAll('.glyph')].map(g=>({{index:Number(g.dataset.index),character:g.dataset.char,file:g.dataset.file,status:g.querySelector('.glyph-status').value}}))}}));const out={{format:'saol-word-segment-feedback-v1',manifest:{json.dumps(manifest_path.name)},exported_at:new Date().toISOString(),words}};const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='saol14-word-segment-feedback.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}};
refresh();
</script>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(cards)} missing={missing} styles={','.join(sorted(set(str(w.get('style')) for w in words)))} manifest={manifest_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
