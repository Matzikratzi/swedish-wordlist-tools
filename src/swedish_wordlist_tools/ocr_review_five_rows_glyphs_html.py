from __future__ import annotations

import argparse
import html
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import ocr_review_row_glyphs_html as legacy
from . import ocr_review_row_glyphs_paint_html as editor
from .ocr_column_row_segmentation import segment_page_rows
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page


def page_positions(jsonl: Path, page_number: int, threshold: int = 210) -> list[tuple[int, int]]:
    rows = list(read_jsonl(jsonl))
    source = source_for_page(rows, page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = _load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    row_map = segment_page_rows(page, threshold=threshold)
    return [
        (column, row_index)
        for column, column_entry in enumerate(row_map["columns"])
        for row_index, _row in enumerate(column_entry.get("rows") or [])
    ]


def window_positions(
    positions: list[tuple[int, int]], current: tuple[int, int], radius: int = 2
) -> list[tuple[int, int]]:
    if current not in positions:
        raise ValueError(f"row {current} is not present on page")
    index = positions.index(current)
    start = max(0, min(index - radius, max(0, len(positions) - (2 * radius + 1))))
    return positions[start : start + 2 * radius + 1]


def neighbour(positions: list[tuple[int, int]], current: tuple[int, int], delta: int) -> tuple[int, int] | None:
    index = positions.index(current) + delta
    if 0 <= index < len(positions):
        return positions[index]
    return None


def row_url(position: tuple[int, int]) -> str:
    return "/?" + urlencode({"column": position[0], "row": position[1]})


def load_window_states(
    jsonl: Path,
    page_number: int,
    positions: list[tuple[int, int]],
    facit: Path,
    threshold: int = 210,
) -> list[dict]:
    # Intentionally re-read facit for every row via load_review_state. After an edit,
    # the redirected GET therefore recomputes all five visible rows with the newest
    # glyph models rather than retaining an editor-session glyph cache.
    states: list[dict] = []
    for index, (column, row_index) in enumerate(positions, start=1):
        print(f"review: räknar om synlig rad {index}/{len(positions)} (kolumn {column}, rad {row_index})", flush=True)
        states.append(legacy.load_review_state(jsonl, page_number, column, row_index, facit, threshold))
    return states


def render_five_row_html(
    states: list[dict],
    active_position: tuple[int, int],
    all_positions: list[tuple[int, int]],
    message: str = "",
) -> str:
    active = next(state for state in states if (state["column"], state["row"]) == active_position)
    document = editor.render_html(active, message)

    previous = neighbour(all_positions, active_position, -1)
    following = neighbour(all_positions, active_position, 1)
    prev_link = f'<a class="navbutton" href="{row_url(previous)}">← Föregående</a>' if previous else '<span class="navbutton disabled">← Föregående</span>'
    next_link = f'<a class="navbutton" href="{row_url(following)}">Nästa →</a>' if following else '<span class="navbutton disabled">Nästa →</span>'

    cards = []
    for state in states:
        position = (state["column"], state["row"])
        active_class = " active" if position == active_position else ""
        exact = state["covered_pixels"] == state["source_pixels"]
        status = "exakt" if exact else f'{state["covered_pixels"]}/{state["source_pixels"]} px'
        cards.append(
            f'<a class="rowcard{active_class}" href="{row_url(position)}">'
            f'<div><b>kol {position[0]} · rad {position[1]}</b> · {html.escape(status)}</div>'
            f'<img src="{state["image"]}" alt="kolumn {position[0]}, rad {position[1]}">'
            f'<div class="rowtext">{html.escape(state.get("text") or "")}</div>'
            '</a>'
        )

    extra_css = """
<style>
.five-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.navbutton{display:inline-block;padding:7px 11px;border:1px solid #888;background:white;color:#171717;text-decoration:none;border-radius:4px}
.navbutton.disabled{opacity:.35}.five-context{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:7px;margin:10px 0 18px;max-width:1200px}
.rowcard{display:block;border:2px solid #bbb;background:white;padding:6px;color:#171717;text-decoration:none;min-width:0}.rowcard.active{border:4px solid #1769d2;padding:4px;background:#eef6ff}
.rowcard img{width:100%;height:58px;object-fit:contain;object-position:left center;image-rendering:pixelated;background:white}.rowtext{font:12px monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
@media(max-width:900px){.five-context{grid-template-columns:1fr}}
</style>
"""
    navigation = (
        '<div class="five-nav">'
        + prev_link
        + next_link
        + f'<a class="navbutton" href="{row_url(active_position)}">↻ Räkna om raderna</a>'
        + '<span>Efter varje sparad glyph räknas alla fem visade rader om automatiskt.</span>'
        + '</div><div class="five-context">'
        + "".join(cards)
        + '</div>'
    )
    keyboard = f"""
<script>
document.addEventListener('keydown', e => {{
  if (e.target && ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft' && {str(previous is not None).lower()}) window.location.href = {repr(row_url(previous) if previous else '/')};
  if (e.key === 'ArrowRight' && {str(following is not None).lower()}) window.location.href = {repr(row_url(following) if following else '/')};
}});
</script>
"""
    document = document.replace("</head>", extra_css + "</head>", 1)
    document = document.replace("<h1>", navigation + "<h1>", 1)
    document = document.replace("</body>", keyboard + "</body>", 1)
    return document


def main() -> int:
    ap = argparse.ArgumentParser(description="Review one editable SAOL row with a five-row live context window.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    positions = page_positions(args.jsonl, args.page, args.threshold)
    initial = (args.column, args.row)
    if initial not in positions:
        raise ValueError(f"initial row {initial} is not present on page {args.page}")
    message = {"text": ""}

    class Handler(BaseHTTPRequestHandler):
        def _position(self) -> tuple[int, int]:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                position = (
                    int((query.get("column") or [str(initial[0])])[0]),
                    int((query.get("row") or [str(initial[1])])[0]),
                )
            except ValueError as exc:
                raise ValueError("column and row must be integers") from exc
            if position not in positions:
                raise ValueError(f"row {position} is not present on page")
            return position

        def _window(self, position: tuple[int, int]) -> list[dict]:
            visible = window_positions(positions, position)
            return load_window_states(args.jsonl, args.page, visible, args.facit, args.threshold)

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                position = self._position()
                body = render_five_row_html(self._window(position), position, positions, message["text"]).encode("utf-8")
                message["text"] = ""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            try:
                position = self._position()
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                active_state = legacy.load_review_state(
                    args.jsonl, args.page, position[0], position[1], args.facit, args.threshold
                )
                message["text"] = legacy.apply_edit(active_state, args.facit, form)
                location = row_url(position)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
                location = row_url(initial)
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}{row_url(initial)}"
    print(url)
    print(f"facit={args.facit} (alla fem synliga rader räknas om mot senaste facit; Ctrl-C avslutar)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
