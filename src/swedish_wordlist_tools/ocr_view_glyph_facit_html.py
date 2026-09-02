from __future__ import annotations

import argparse
import html
import threading
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .ocr_glyph_matcher import GlyphModel, load_facit


STYLE_COLUMNS = (
    ("bold", "b", "fet"),
    ("italic", "i", "kursiv"),
    ("roman", "r", "rak"),
)


def _label_sort_key(label: str) -> tuple:
    alphabet = "abcdefghijklmnopqrstuvwxyzåäö"
    folded = label.casefold()
    if len(folded) == 1 and folded in alphabet:
        return (0, alphabet.index(folded), label != folded, label)
    if len(label) == 1:
        return (1, ord(label), label)
    return (2, folded, label)


def _model_sort_key(model: GlyphModel) -> tuple:
    return (
        model.width,
        model.min_y,
        model.max_y,
        len(model.pixels),
        -model.sources,
        tuple(sorted(model.pixels)),
    )


def _glyph_svg(model: GlyphModel, *, pixel: int = 12, margin: int = 1) -> str:
    min_x = min(x for x, _ in model.pixels)
    max_x = max(x for x, _ in model.pixels)
    min_y = min(y for _, y in model.pixels)
    max_y = max(y for _, y in model.pixels)
    x0 = min_x - margin
    x1 = max_x + margin
    y0 = min_y - margin
    y1 = max_y + margin
    cols = x1 - x0 + 1
    rows = y1 - y0 + 1
    width = cols * pixel
    height = rows * pixel

    parts = [
        f'<svg class="glyph-grid" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(model.label)} {html.escape(model.style)}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
    ]
    for col in range(cols + 1):
        x = col * pixel
        parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" class="grid-line"/>')
    for row in range(rows + 1):
        y = row * pixel
        parts.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" class="grid-line"/>')

    # The baseline is y=0 in facit coordinates. Draw it between pixel rows -1
    # and 0, i.e. on the top edge of the baseline row.
    if y0 <= 0 <= y1:
        baseline_y = (0 - y0) * pixel
        parts.append(
            f'<line x1="0" y1="{baseline_y}" x2="{width}" y2="{baseline_y}" '
            'class="baseline-line"/>'
        )

    for x, y in sorted(model.pixels, key=lambda p: (p[1], p[0])):
        sx = (x - x0) * pixel
        sy = (y - y0) * pixel
        parts.append(
            f'<rect x="{sx + 0.5}" y="{sy + 0.5}" width="{pixel - 1}" '
            f'height="{pixel - 1}" class="ink"/>'
        )
    parts.append("</svg>")

    meta = f"{model.width}×{max_y - min_y + 1}px · {len(model.pixels)} svarta · {model.sources} källor"
    return (
        '<div class="variant">'
        + "".join(parts)
        + f'<div class="variant-meta">{html.escape(meta)}</div>'
        + "</div>"
    )


def build_facit_table(models: list[GlyphModel], *, pixel: int = 12) -> str:
    grouped: dict[str, dict[str, list[GlyphModel]]] = defaultdict(lambda: defaultdict(list))
    for model in models:
        grouped[model.label][model.style].append(model)

    known_styles = {style for style, _short, _title in STYLE_COLUMNS}
    extra_styles = sorted({model.style for model in models} - known_styles)
    columns = list(STYLE_COLUMNS) + [(style, style, style) for style in extra_styles]

    rows = []
    for label in sorted(grouped, key=_label_sort_key):
        cells = [f'<th class="row-label" scope="row">{html.escape(label) or "∅"}</th>']
        for style, _short, _title in columns:
            variants = sorted(grouped[label].get(style, []), key=_model_sort_key)
            if variants:
                body = "".join(_glyph_svg(model, pixel=pixel) for model in variants)
                count = f'<div class="variant-count">{len(variants)} variant' + ("er" if len(variants) != 1 else "") + "</div>"
                cells.append(f'<td class="glyph-cell">{count}<div class="variants">{body}</div></td>')
            else:
                cells.append('<td class="glyph-cell empty">—</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    header_cells = ['<th class="corner">tecken</th>']
    for _style, short, title in columns:
        header_cells.append(
            f'<th class="style-head"><span class="style-short">{html.escape(short)}</span>'
            f'<span>{html.escape(title)}</span></th>'
        )

    return (
        '<table class="facit-table"><thead><tr>'
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def render_page(models: list[GlyphModel], facit_path: Path, *, pixel: int = 12) -> str:
    labels = len({model.label for model in models})
    return f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SAOL glyph-facit</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
body {{ margin: 0; background: #f4f4f4; color: #111; }}
header {{ position: sticky; top: 0; z-index: 5; padding: 10px 16px; background: rgba(255,255,255,.96); border-bottom: 1px solid #bbb; }}
h1 {{ margin: 0 0 3px; font-size: 20px; }}
.summary {{ font-size: 13px; color: #444; }}
.wrap {{ padding: 12px; overflow: auto; }}
.facit-table {{ border-collapse: separate; border-spacing: 0; background: white; box-shadow: 0 1px 5px #bbb; }}
th, td {{ border-right: 1px solid #aaa; border-bottom: 1px solid #aaa; vertical-align: top; }}
thead th {{ position: sticky; top: 66px; z-index: 4; background: #ececec; border-top: 1px solid #aaa; }}
.corner {{ left: 0; z-index: 6; min-width: 62px; }}
.row-label {{ position: sticky; left: 0; z-index: 3; padding: 14px 10px; min-width: 62px; background: #f8f8f8; text-align: center; font-size: 24px; }}
.style-head {{ min-width: 180px; padding: 7px 10px; text-align: left; white-space: nowrap; }}
.style-short {{ display: inline-block; min-width: 28px; font-size: 22px; font-weight: 800; }}
.style-head span:last-child {{ font-size: 12px; font-weight: 500; color: #555; }}
.glyph-cell {{ padding: 7px 10px 10px; min-width: 180px; }}
.glyph-cell.empty {{ text-align: center; vertical-align: middle; color: #aaa; font-size: 24px; }}
.variant-count {{ margin-bottom: 5px; font-size: 11px; color: #666; }}
.variants {{ display: flex; align-items: flex-start; gap: 14px; width: max-content; }}
.variant {{ flex: none; padding: 5px; border: 1px solid #ddd; background: #fafafa; }}
.glyph-grid {{ display: block; image-rendering: pixelated; }}
.grid-line {{ stroke: #d0d0d0; stroke-width: 1; shape-rendering: crispEdges; }}
.baseline-line {{ stroke: #d22; stroke-width: 2; shape-rendering: crispEdges; }}
.ink {{ fill: #111; shape-rendering: crispEdges; }}
.variant-meta {{ margin-top: 4px; font: 10px/1.2 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: nowrap; color: #555; }}
</style>
</head>
<body>
<header>
<h1>SAOL glyph-facit</h1>
<div class="summary">{len(models)} glyphmodeller · {labels} etiketter · {html.escape(str(facit_path))} · rutstorlek {pixel}px</div>
</header>
<div class="wrap">{build_facit_table(models, pixel=pixel)}</div>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Visa SAOL-glyphfacit som en tabell med stora pixelrutnät.")
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--pixel", type=int, default=12, help="storlek i CSS-pixlar för varje facitpixel")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if args.pixel < 4 or args.pixel > 40:
        raise ValueError("--pixel måste vara 4..40")

    models = load_facit(args.facit)
    page = render_page(models, args.facit, pixel=args.pixel).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlparse(self.path).path not in {"", "/"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, fmt, *values):
            print("facit-view: " + (fmt % values), flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    print(f"facit-view: {len(models)} modeller; Ctrl-C avslutar", flush=True)
    if not args.no_browser:
        threading.Timer(0.15, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
