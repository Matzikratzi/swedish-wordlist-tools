from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a static HTML review page for ambiguous SAOL OCR glyphs.")
    p.add_argument("comparison_json", type=Path, help="JSON output from ocr_glyph_compare")
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    data = json.loads(args.comparison_json.read_text(encoding="utf-8"))
    observed = data.get("observed_crop")
    context = data.get("context_crop")
    comparisons = data.get("comparisons", [])

    cards = []
    for item in comparisons:
        fname = item.get("template")
        img = ""
        if fname:
            path = args.templates / fname
            if path.exists():
                img = f'<img class="glyph" src="{_data_uri(path)}" alt="template {html.escape(str(item.get("candidate", "?")))}">'
        cards.append(
            "<div class=card>"
            f"<h3>Kandidat: {html.escape(str(item.get('candidate', '?')))}</h3>"
            f"{img}"
            f"<p>pixel-score: <b>{html.escape(str(item.get('score', '')))}</b></p>"
            f"<p>mall: {html.escape(str(fname or ''))}</p>"
            "</div>"
        )

    observed_html = "<p>Ingen observerad crop sparades.</p>"
    if observed:
        path = Path(observed)
        if path.exists():
            observed_html = f'<img class="glyph observed" src="{_data_uri(path)}" alt="observed glyph">'

    context_html = ""
    if context:
        path = Path(context)
        if path.exists():
            context_html = f'<img class="context" src="{_data_uri(path)}" alt="word context">'

    best = data.get("best") or {}
    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL OCR review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}}
.card{{border:1px solid #bbb;border-radius:10px;padding:1rem}}
.glyph{{image-rendering:pixelated;transform:scale(2);transform-origin:left top;margin:0 2rem 2rem 0;background:white;border:1px solid #ddd}}
.context{{image-rendering:pixelated;display:block;max-width:100%;transform:scale(2);transform-origin:left top;margin:0 0 3rem 0;border:1px solid #ddd}}
.meta{{background:#f5f5f5;padding:1rem;border-radius:8px;margin-bottom:1rem}}
code{{font-size:13px}}
</style>
<h1>SAOL OCR glyph review</h1>
<div class="meta">
<p><b>OCR-ord:</b> {html.escape(str(data.get('word', '')))}</p>
<p><b>Stilklass:</b> {html.escape(str(data.get('style', '')))}</p>
<p><b>Position:</b> {html.escape(str(data.get('index', '')))} &nbsp; <b>OCR-tecken:</b> {html.escape(str(data.get('ocr_character', '')))}</p>
<p><b>Ord-bbox:</b> <code>{html.escape(str(data.get('word_bbox', '')))}</code></p>
<p><b>Tecken-bbox:</b> <code>{html.escape(str(data.get('glyph_bbox_in_image', '')))}</code></p>
<p><b>Bästa kandidat:</b> {html.escape(str(best.get('candidate', '')))} &nbsp; <b>marginal:</b> {html.escape(str(data.get('margin', '')))}</p>
</div>
<h2>Kontext</h2>
{context_html}
<h2>Observerat tecken</h2>
{observed_html}
<h2>Kända SAOL-mallar</h2>
<div class="grid">{''.join(cards)}</div>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
