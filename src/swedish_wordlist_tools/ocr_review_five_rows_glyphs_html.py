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

PACKET_SIZE = 5


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


def packet_positions(
    positions: list[tuple[int, int]], current: tuple[int, int], size: int = PACKET_SIZE
) -> list[tuple[int, int]]:
    if current not in positions:
        raise ValueError(f"row {current} is not present on page")
    index = positions.index(current)
    start = (index // size) * size
    return positions[start : start + size]


def window_positions(
    positions: list[tuple[int, int]], current: tuple[int, int], radius: int = 2
) -> list[tuple[int, int]]:
    """Backward-compatible alias for the old five-row helper.

    The UI now uses fixed five-row packets rather than a sliding ±2 window.
    """
    return packet_positions(positions, current, size=2 * radius + 1)


def neighbour(positions: list[tuple[int, int]], current: tuple[int, int], delta: int) -> tuple[int, int] | None:
    index = positions.index(current) + delta
    if 0 <= index < len(positions):
        return positions[index]
    return None


def is_defective(state: dict) -> bool:
    return int(state.get("covered_pixels") or 0) != int(state.get("source_pixels") or 0)


def defect_packet(
    positions: list[tuple[int, int]],
    anchor: tuple[int, int],
    state_for,
    *,
    direction: int = 1,
    size: int = PACKET_SIZE,
) -> list[tuple[int, int]]:
    """Find up to ``size`` rows with unknown glyph pixels from an anchor.

    The caller supplies a cached state loader.  This makes defect-only browsing
    lazy: we analyse only enough physical rows to find the next five defects,
    rather than rescanning the entire page before the editor can open.
    """
    if anchor not in positions:
        raise ValueError(f"row {anchor} is not present on page")
    start = positions.index(anchor)
    indices = range(start, len(positions)) if direction >= 0 else range(start, -1, -1)
    found: list[tuple[int, int]] = []
    for index in indices:
        position = positions[index]
        if is_defective(state_for(position)):
            found.append(position)
            if len(found) == size:
                break
    if direction < 0:
        found.reverse()
    return found


def row_url(
    position: tuple[int, int],
    *,
    mode: str = "all",
    anchor: tuple[int, int] | None = None,
    scan: str = "forward",
) -> str:
    values: dict[str, object] = {"column": position[0], "row": position[1]}
    if mode != "all":
        values["mode"] = mode
    if anchor is not None:
        values["anchor_column"] = anchor[0]
        values["anchor_row"] = anchor[1]
    if scan != "forward":
        values["scan"] = scan
    return "/?" + urlencode(values)


def render_five_row_html(
    states: list[dict],
    active_position: tuple[int, int],
    all_positions: list[tuple[int, int]],
    message: str = "",
    *,
    mode: str = "all",
    anchor: tuple[int, int] | None = None,
) -> str:
    if not states:
        raise ValueError("no rows to display")
    visible = [(state["column"], state["row"]) for state in states]
    if active_position not in visible:
        active_position = visible[0]
    active = next(state for state in states if (state["column"], state["row"]) == active_position)
    document = editor.render_html(active, message)

    first_index = all_positions.index(visible[0])
    last_index = all_positions.index(visible[-1])
    if mode == "defects":
        previous_anchor = all_positions[first_index - 1] if first_index > 0 else None
        next_anchor = all_positions[last_index + 1] if last_index + 1 < len(all_positions) else None
        previous_url = (
            row_url(previous_anchor, mode=mode, anchor=previous_anchor, scan="backward")
            if previous_anchor else None
        )
        next_url = (
            row_url(next_anchor, mode=mode, anchor=next_anchor, scan="forward")
            if next_anchor else None
        )
    else:
        previous_position = all_positions[max(0, first_index - PACKET_SIZE)] if first_index > 0 else None
        next_position = all_positions[last_index + 1] if last_index + 1 < len(all_positions) else None
        previous_url = row_url(previous_position) if previous_position else None
        next_url = row_url(next_position) if next_position else None

    prev_link = f'<a class="navbutton" href="{previous_url}">← Fem föregående</a>' if previous_url else '<span class="navbutton disabled">← Fem föregående</span>'
    next_link = f'<a class="navbutton" href="{next_url}">Fem nästa →</a>' if next_url else '<span class="navbutton disabled">Fem nästa →</span>'

    packet_anchor = anchor or visible[0]
    cards = []
    for state in states:
        position = (state["column"], state["row"])
        active_class = " active" if position == active_position else ""
        exact = not is_defective(state)
        status = "exakt" if exact else f'{state["covered_pixels"]}/{state["source_pixels"]} px'
        target = row_url(position, mode=mode, anchor=packet_anchor)
        cards.append(
            f'<a class="rowcard{active_class}" href="{target}">'
            f'<div><b>kol {position[0]} · rad {position[1]}</b> · {html.escape(status)}</div>'
            f'<img src="{state["image"]}" alt="kolumn {position[0]}, rad {position[1]}">'
            f'<div class="rowtext">{html.escape(state.get("text") or "")}</div>'
            '</a>'
        )

    if mode == "defects":
        mode_link = row_url(active_position, mode="all")
        mode_button = f'<a class="navbutton modeon" href="{mode_link}">☑ Bara defekta</a>'
        mode_explanation = "Visar endast rader med okända pixlar."
    else:
        mode_link = row_url(active_position, mode="defects", anchor=active_position)
        mode_button = f'<a class="navbutton" href="{mode_link}">☐ Bara defekta</a>'
        mode_explanation = "Visar alla fysiska rader."

    refresh_url = row_url(active_position, mode=mode, anchor=packet_anchor)
    extra_css = """
<style>
.five-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.navbutton{display:inline-block;padding:7px 11px;border:1px solid #888;background:white;color:#171717;text-decoration:none;border-radius:4px}
.navbutton.disabled{opacity:.35}.navbutton.modeon{font-weight:700;background:#eef6ff;border-color:#1769d2}
.five-context{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:7px;margin:10px 0 18px;max-width:1200px}
.rowcard{display:block;border:2px solid #bbb;background:white;padding:6px;color:#171717;text-decoration:none;min-width:0}.rowcard.active{border:4px solid #1769d2;padding:4px;background:#eef6ff}
.rowcard img{width:100%;height:58px;object-fit:contain;object-position:left center;image-rendering:pixelated;background:white}.rowtext{font:12px monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
@media(max-width:900px){.five-context{grid-template-columns:1fr}}
</style>
"""
    navigation = (
        '<div class="five-nav">'
        + prev_link
        + next_link
        + mode_button
        + f'<a class="navbutton" href="{refresh_url}&refresh=1">↻ Räkna om paketet</a>'
        + f'<span>{html.escape(mode_explanation)} Byte mellan de fem använder redan analyserade rader.</span>'
        + '</div><div class="five-context">'
        + "".join(cards)
        + '</div>'
    )
    keyboard = f"""
<script>
document.addEventListener('keydown', e => {{
  if (e.target && ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft' && {str(previous_url is not None).lower()}) window.location.href = {repr(previous_url or '/')};
  if (e.key === 'ArrowRight' && {str(next_url is not None).lower()}) window.location.href = {repr(next_url or '/')};
}});
</script>
"""
    document = document.replace("</head>", extra_css + "</head>", 1)
    document = document.replace("<h1>", navigation + "<h1>", 1)
    document = document.replace("</body>", keyboard + "</body>", 1)
    return document


def main() -> int:
    ap = argparse.ArgumentParser(description="Review SAOL glyphs in fast five-row packets, optionally defects only.")
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
    state_cache: dict[tuple[int, int], dict] = {}

    def clear_analysis_cache(reason: str) -> None:
        if state_cache:
            print(f"review: tömmer {len(state_cache)} analyserade rader ({reason})", flush=True)
        state_cache.clear()

    def state_for(position: tuple[int, int]) -> dict:
        state = state_cache.get(position)
        if state is not None:
            return state
        column, row_index = position
        print(f"review: analyserar kolumn {column}, rad {row_index} ...", flush=True)
        state = legacy.load_review_state(
            args.jsonl, args.page, column, row_index, args.facit, args.threshold
        )
        state_cache[position] = state
        status = "exakt" if not is_defective(state) else f"defekt {state['covered_pixels']}/{state['source_pixels']}"
        print(f"review: kolumn {column}, rad {row_index}: {status}", flush=True)
        return state

    class Handler(BaseHTTPRequestHandler):
        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query)

        def _position(self, query: dict[str, list[str]]) -> tuple[int, int]:
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

        def _anchor(self, query: dict[str, list[str]], position: tuple[int, int]) -> tuple[int, int]:
            if "anchor_column" not in query or "anchor_row" not in query:
                return position
            try:
                anchor = (int(query["anchor_column"][0]), int(query["anchor_row"][0]))
            except ValueError as exc:
                raise ValueError("anchor column and row must be integers") from exc
            return anchor if anchor in positions else position

        def _visible(self, query: dict[str, list[str]], position: tuple[int, int]) -> tuple[list[tuple[int, int]], str, tuple[int, int]]:
            mode = (query.get("mode") or ["all"])[0]
            if mode not in {"all", "defects"}:
                mode = "all"
            anchor = self._anchor(query, position)
            if mode == "defects":
                direction = -1 if (query.get("scan") or ["forward"])[0] == "backward" else 1
                visible = defect_packet(positions, anchor, state_for, direction=direction)
                if not visible:
                    return [], mode, anchor
                anchor = visible[0]
            else:
                visible = packet_positions(positions, position)
                anchor = visible[0]
            return visible, mode, anchor

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                query = self._query()
                if (query.get("refresh") or ["0"])[0] == "1":
                    clear_analysis_cache("manuell omräkning")
                position = self._position(query)
                visible, mode, anchor = self._visible(query, position)
                if not visible:
                    body = b"<html><body><h1>Inga defekta rader kvar.</h1><a href='/'>Visa alla rader</a></body></html>"
                else:
                    if position not in visible:
                        position = visible[0]
                    states = [state_for(item) for item in visible]
                    body = render_five_row_html(
                        states, position, positions, message["text"], mode=mode, anchor=anchor
                    ).encode("utf-8")
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
                query = self._query()
                position = self._position(query)
                mode = (query.get("mode") or ["all"])[0]
                anchor = self._anchor(query, position)
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                active_state = state_for(position)
                message["text"] = legacy.apply_edit(active_state, args.facit, form)
                clear_analysis_cache("facit ändrat")
                location = row_url(position, mode=mode, anchor=anchor)
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
    print(
        f"facit={args.facit} (femrader paketvis; radanalys återanvänds tills facit ändras; Ctrl-C avslutar)"
    )
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
