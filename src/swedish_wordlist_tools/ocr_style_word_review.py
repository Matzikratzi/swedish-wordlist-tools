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
    ap = argparse.ArgumentParser(
        description="Generate a static visual QC page for whole-word segmented roman/italic glyphs."
    )
    ap.add_argument("library", type=Path)
    ap.add_argument("--jsonl", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--style", choices=("roman", "italic"))
    args = ap.parse_args()

    manifest_path = args.library / "manifest-word-segments.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = _load_sources(args.jsonl)

    words = [w for w in payload.get("words", []) if isinstance(w, dict)]
    if args.style:
        words = [w for w in words if w.get("style") == args.style]

    cards: list[str] = []
    missing = 0
    for row in words:
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
            rel = g.get("file")
            if not isinstance(rel, str):
                continue
            path = args.library / rel
            if not path.exists():
                missing += 1
                continue
            glyph_html.append(
                '<figure class="glyph">'
                f'<div class="gframe"><img src="{_data_uri(path)}" alt="{html.escape(ch)}"></div>'
                f'<figcaption>{html.escape(ch)}</figcaption>'
                '</figure>'
            )

        source = sources.get(str(subnr))
        source_html = (
            f'<a href="{html.escape(source, quote=True)}" target="_blank" rel="noopener">faksimil sida {html.escape(str(page))} ↗</a>'
            if source else f'<span>sida {html.escape(str(page))}</span>'
        )
        searchable = f"{style} {expected} {page} {subnr}".lower()
        cards.append(
            f'<article class="word" data-search="{html.escape(searchable, quote=True)}">'
            '<header>'
            f'<strong>{html.escape(expected)}</strong>'
            f'<span class="badge">{html.escape(style)}</span>'
            f'<span>subnr {html.escape(str(subnr))}</span>'
            f'{source_html}'
            '</header>'
            '<div class="comparison">'
            '<div class="whole"><div class="label">hela ordet</div>'
            f'<div class="wframe"><img src="{_data_uri(word_path)}" alt="{html.escape(expected)}"></div></div>'
            '<div class="segments"><div class="label">segment</div><div class="glyphrow">'
            + ''.join(glyph_html) +
            '</div></div></div>'
            '</article>'
        )

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL word-segment QC</title>
<style>
:root{{--scale:{max(1,args.scale)};}}
*{{box-sizing:border-box}} body{{font-family:system-ui,sans-serif;margin:24px;background:#f4f4f4;color:#151515}}
h1{{margin-bottom:.3rem}} .intro{{color:#555;max-width:900px}} .toolbar{{position:sticky;top:0;padding:10px 0;background:#f4f4f4ee;z-index:5}}
input{{font:inherit;padding:.5rem .7rem;width:28rem;max-width:100%;border:1px solid #aaa;border-radius:6px}}
.word{{background:white;border:1px solid #ccc;border-radius:9px;padding:14px;margin:14px 0}}
.word header{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}} .word header strong{{font-size:22px}}
.badge{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;padding:3px 7px;border:1px solid #999;border-radius:999px}}
.comparison{{display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap}} .label{{font-size:12px;color:#666;margin-bottom:7px}}
.wframe,.gframe{{background:#eee;border:1px solid #aaa;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.wframe{{min-width:260px;height:100px}} .wframe img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}
.glyphrow{{display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}} .glyph{{margin:0;width:78px;text-align:center}}
.gframe{{width:78px;height:76px}} .gframe img{{image-rendering:pixelated;transform:scale(var(--scale));transform-origin:center}}
.glyph figcaption{{font-size:24px;font-weight:700;line-height:1.2;margin-top:4px}} .hidden{{display:none}}
a{{color:#0645ad}}
</style>
<h1>SAOL word-segment QC</h1>
<p class="intro">{len(cards)} ord. Kontrollera att segmenten under varje ord verkligen motsvarar bokstäverna som står under dem. Fel segmentgräns är viktigare att fånga än små rasterartefakter. Saknade filer: {missing}.</p>
<div class="toolbar"><input id="q" placeholder="Filtrera på ord, stil, sida eller subnr…"></div>
{''.join(cards)}
<script>
const q=document.getElementById('q');
q.addEventListener('input',()=>{{const s=q.value.toLowerCase();document.querySelectorAll('.word').forEach(w=>w.classList.toggle('hidden',!w.dataset.search.includes(s)));}});
</script>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    print(f"words={len(cards)} missing={missing} styles={','.join(sorted(set(str(w.get('style')) for w in words)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
