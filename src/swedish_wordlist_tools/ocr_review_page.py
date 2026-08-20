from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def _data_uri(path: Path) -> str:
    mime = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a static HTML review page for ambiguous SAOL OCR glyphs.")
    p.add_argument("comparison_json", type=Path, help="JSON output from ocr_glyph_compare")
    p.add_argument("--templates", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    data = json.loads(args.comparison_json.read_text(encoding="utf-8"))
    observed = data.get("observed_crop")
    candidates = data.get("candidates", [])

    cards = []
    for item in candidates:
        fname = item.get("template") or item.get("output")
        img = ""
        if fname:
            path = args.templates / fname
            if path.exists():
                img = f'<img src="{_data_uri(path)}" alt="template">'
        cards.append(
            "<div class=card>"
            f"<h3>{html.escape(str(item.get('character', item.get('candidate', '?'))))}</h3>"
            f"{img}"
            f"<pre>{html.escape(json.dumps(item, ensure_ascii=False, indent=2))}</pre>"
            "</div>"
        )

    observed_html = ""
    if observed:
        path = Path(observed)
        if path.exists():
            observed_html = f'<img class="observed" src="{_data_uri(path)}" alt="observed">'

    doc = f'''<!doctype html>
<meta charset="utf-8">
<title>SAOL OCR review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}}
.card{{border:1px solid #bbb;border-radius:10px;padding:1rem}}
img{{image-rendering:pixelated;transform:scale(4);transform-origin:left top;margin:0 0 3rem 0}}
pre{{white-space:pre-wrap;font-size:12px}}
.observed{{display:block;margin-bottom:4rem}}
</style>
<h1>SAOL OCR glyph review</h1>
<p><b>Expected:</b> {html.escape(str(data.get('expected', '')))} &nbsp; <b>OCR:</b> {html.escape(str(data.get('observed_ocr', '')))}</p>
{observed_html}
<div class="grid">{''.join(cards)}</div>
'''
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
