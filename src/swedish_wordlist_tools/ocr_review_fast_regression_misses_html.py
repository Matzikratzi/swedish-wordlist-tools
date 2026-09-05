from __future__ import annotations

"""Serve all fast-regression misses as three-row pixel-grid cards.

The gallery deliberately reuses the same neighbor raster data as the full glyph
reviewer's "Visa tre rader" view: previous physical row, target row, next row,
with the same 7x pixel grid and row-boundary overlays.  It is read-only and does
not alter facit or ownership beyond the cheap boundary repairs already performed
by the fast regression scan.
"""

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_fast_regression_scan import scan_page_fast
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_neighbor_row_raster import add_neighbor_row_raster


def _card_state(context: dict, position: tuple[int, int], models) -> dict:
    """Load the current owned row and attach the established three-row raster."""
    state = page_editor._load_owned_row_state(context, position, models)
    return add_neighbor_row_raster(context, state, probe_y=8)


def _render(states: list[dict], *, pages: list[int]) -> str:
    payload = []
    for index, state in enumerate(states):
        payload.append(
            {
                "id": index,
                "page": int(state.get("page") or 0),
                "column": int(state.get("column") or 0),
                "row": int(state.get("row") or 0),
                "image": state.get("neighbor_raster_image"),
                "width": int(state.get("neighbor_raster_width") or 0),
                "height": int(state.get("neighbor_raster_height") or 0),
                "boundaries": list(state.get("neighbor_row_boundaries") or []),
                "core_top": int(state.get("neighbor_core_top") or 0),
                "core_bottom": int(state.get("neighbor_core_bottom") or 0),
                "source_pixels": int(state.get("source_pixels") or 0),
                "covered_pixels": int(state.get("covered_pixels") or 0),
                "fully_exact": bool(state.get("fully_exact")),
                "text": str(state.get("text") or ""),
            }
        )

    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page_label = ", ".join(map(str, pages))
    return f'''<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>SAOL fast-regression – tre-radersmissar</title>
<style>
:root {{ color-scheme: light; }}
body {{ font-family: system-ui, sans-serif; margin: 18px; background:#f5f5f5; color:#111; }}
h1 {{ margin:0 0 4px; font-size:22px; }}
.summary {{ margin:0 0 18px; color:#444; }}
.card {{ background:#fff; border:1px solid #bbb; border-radius:8px; margin:0 0 22px; padding:12px; overflow:auto; }}
.card h2 {{ font-size:16px; margin:0 0 4px; }}
.meta {{ font:12px ui-monospace, SFMono-Regular, Menlo, monospace; color:#444; margin-bottom:8px; }}
.canvas-wrap {{ display:inline-block; border:1px solid #aaa; background:#fff; padding:4px; }}
canvas {{ display:block; image-rendering:pixelated; }}
.legend {{ font-size:12px; margin:6px 0 0; color:#555; }}
</style>
</head>
<body>
<h1>Fast-regression: olösta tre-radersgrupper</h1>
<p class="summary">Sidor {html.escape(page_label)} · {len(payload)} missar · samma raster som <b>Visa tre rader</b>.</p>
<div id="cards"></div>
<script>
const STATES={data};
const SCALE=7, TOP=34;
const root=document.getElementById('cards');
function make(tag, cls, text) {{ const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; }}
for(const S of STATES) {{
  const card=make('section','card');
  card.appendChild(make('h2','',`Sida ${{S.page}} · kolumn ${{S.column}} · rad ${{S.row}}`));
  card.appendChild(make('div','meta',`coverage=${{S.covered_pixels}}/${{S.source_pixels}} exact=${{S.fully_exact?1:0}}`));
  const wrap=make('div','canvas-wrap');
  const canvas=document.createElement('canvas');
  wrap.appendChild(canvas); card.appendChild(wrap);
  card.appendChild(make('div','legend','Röda linjer = radgränser. Rutnät = en källpixel per ruta. Målrad är mittenraden.'));
  root.appendChild(card);

  const ctx=canvas.getContext('2d');
  const img=new Image(); img.src=S.image;
  img.onload=()=>{{
    canvas.width=S.width*SCALE;
    canvas.height=S.height*SCALE+TOP;
    ctx.imageSmoothingEnabled=false;
    ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(img,0,TOP,S.width*SCALE,S.height*SCALE);

    ctx.save();ctx.strokeStyle='rgba(70,70,70,.22)';ctx.lineWidth=1;
    for(let x=0;x<=S.width;x++){{const xx=x*SCALE+.5;ctx.beginPath();ctx.moveTo(xx,TOP);ctx.lineTo(xx,TOP+S.height*SCALE);ctx.stroke();}}
    for(let y=0;y<=S.height;y++){{const yy=TOP+y*SCALE+.5;ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(S.width*SCALE,yy);ctx.stroke();}}
    ctx.restore();

    ctx.save();ctx.strokeStyle='rgba(190,25,25,.95)';ctx.lineWidth=2;
    for(const entry of S.boundaries){{
      const yy=entry[0], label=entry[1]; const y=TOP+yy*SCALE+.5;
      ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();
      ctx.fillStyle='rgba(190,25,25,.95)';ctx.font='11px monospace';ctx.fillText(label,4,Math.max(11,y-2));
    }}
    ctx.restore();
  }};
}}
</script>
</body>
</html>'''


def build_gallery(jsonl: Path, facit: Path, pages: list[int], *, threshold: int, boundary_radius: int) -> str:
    models = load_facit_with_typography(facit)
    states: list[dict] = []
    for page in pages:
        context = page_editor.build_page_context_pixel_array(jsonl, page, threshold)
        context["quiet_successful_ownership"] = True
        fast_results = scan_page_fast(context, models, boundary_radius=boundary_radius)
        misses = [result for result in fast_results if not result.exact]
        print(f"miss-gallery: page {page}: {len(misses)} missar", flush=True)
        for miss in misses:
            states.append(_card_state(context, (miss.column, miss.row), models))
    return _render(states, pages=pages)


def main() -> int:
    ap = argparse.ArgumentParser(description="Webbgalleri med tre-raders pixelraster för fast-regressionsmissar.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--boundary-radius", type=int, default=6)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8767)
    args = ap.parse_args()

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    document = build_gallery(
        args.jsonl,
        args.facit,
        pages,
        threshold=args.threshold,
        boundary_radius=args.boundary_radius,
    ).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, fmt, *values):
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"http://{args.host}:{args.port}/", flush=True)
    print(f"miss-gallery: {len(pages)} sidor; Ctrl-C avslutar", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
