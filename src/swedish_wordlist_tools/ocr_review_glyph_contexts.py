from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an HTML review of harvested glyphs in their original SAOL context."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--context-x", type=int, default=70)
    parser.add_argument("--context-y", type=int, default=28)
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    sources = data.get("template_sources", {})
    args.out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = args.out_dir / "context"
    image_dir.mkdir(exist_ok=True)

    rows: list[dict[str, object]] = []
    for n, (output, meta) in enumerate(sorted(sources.items()), 1):
        page_image = Path(str(meta["page_image"]))
        x, y, w, h = map(int, meta["page_bbox"])
        with Image.open(page_image) as im0:
            im = im0.convert("RGB")
            x0 = max(0, x - args.context_x)
            y0 = max(0, y - args.context_y)
            x1 = min(im.width, x + w + args.context_x)
            y1 = min(im.height, y + h + args.context_y)
            crop = im.crop((x0, y0, x1, y1))
        draw = ImageDraw.Draw(crop)
        rx0, ry0 = x - x0, y - y0
        draw.rectangle((rx0, ry0, rx0 + w - 1, ry0 + h - 1), outline="red", width=2)
        name = f"{n:05d}.png"
        crop.save(image_dir / name)
        rows.append({
            "context": f"context/{name}",
            "glyph": str(Path("..") / output),
            "output": output,
            **meta,
        })

    cards = []
    for row in rows:
        cards.append(
            '<div class="card">'
            f'<div class="title"><b>{html.escape(str(row.get("character", "")))}</b> '
            f'{html.escape(str(row.get("style", "")))} · sida {row.get("page")} · '
            f'{html.escape(str(row.get("expected_word", "")))}</div>'
            f'<img class="context" src="{html.escape(str(row["context"]))}">'
            f'<div class="meta">{html.escape(str(row.get("source_word", "")))} · '
            f'{html.escape(str(row.get("position_kind", "")))} · '
            f'{html.escape(str(row.get("page_bbox", "")))}</div>'
            '</div>'
        )

    doc = """<!doctype html><meta charset="utf-8">
<title>SAOL glyph context review</title>
<style>
body{font-family:sans-serif;margin:20px;background:#eee}
h1{margin-bottom:4px}.summary{margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
.card{background:white;padding:10px;border:1px solid #bbb}
.title{font-size:16px;margin-bottom:6px}.context{max-width:100%;image-rendering:auto}
.meta{font:12px monospace;margin-top:5px;color:#444;overflow-wrap:anywhere}
</style>
<h1>SAOL glyph context review</h1>
"""
    doc += f'<div class="summary">{len(rows)} skördade tecken. Röd box = sparad glyph.</div>\n'
    doc += '<div class="grid">' + "\n".join(cards) + "</div>\n"
    (args.out_dir / "index.html").write_text(doc, encoding="utf-8")
    print(f"{len(rows)} glypher: {args.out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
