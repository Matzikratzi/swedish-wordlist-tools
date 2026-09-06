from __future__ import annotations

"""Unified three-row pixel-array glyph editor with all-row or queue navigation."""

import argparse
import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from PIL import Image

from . import ocr_neighbor_row_raster as neighbor_raster
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT
from .ocr_page_cached_fast_path import bind_page_candidates
from .ocr_priority_fast_path import classify_row_start, observe_row_layout, set_row_priority_hint

Position = tuple[int, int, int]  # page, column, row


def _load_queue(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != QUEUE_FORMAT:
        raise ValueError(
            f"unsupported review queue format {payload.get('format')!r}; expected {QUEUE_FORMAT!r}"
        )
    rows = list(payload.get("rows") or [])
    if not rows:
        raise ValueError(f"review queue is empty: {path}")
    return rows


def _snapshot_text(label: str, snapshot: dict | None) -> str:
    if snapshot is None:
        return f"<b>{html.escape(label)}:</b> saknas"
    return (
        f"<b>{html.escape(label)}:</b> "
        f"pixels={int(snapshot.get('source_pixels') or 0)} "
        f"covered={int(snapshot.get('covered_pixels') or 0)} "
        f"exact={bool(snapshot.get('exact', False))} "
        f"text=<code>{html.escape(repr(str(snapshot.get('text') or '')))}</code>"
    )


def _mismatch_banner(state: dict) -> str:
    mismatch = state.get("benchmark_mismatch")
    queue_position = state.get("queue_position")
    queue_line = ""
    if queue_position:
        queue_line = f"<div><b>KÖPOST:</b> {int(queue_position[0])}/{int(queue_position[1])}</div>"
    if not mismatch:
        return queue_line
    current = {
        "text": str(state.get("text") or ""),
        "source_pixels": int(state.get("source_pixels") or 0),
        "covered_pixels": int(state.get("covered_pixels") or 0),
        "exact": bool(state.get("fully_exact", False)),
    }
    why = html.escape(str(mismatch.get("why") or "okänd referensavvikelse"))
    return (
        '<div style="margin:8px 0 14px;padding:10px 12px;border:2px solid #b66;'
        'background:#fff5f0;font:14px/1.45 sans-serif">'
        f"{queue_line}"
        f"<div><b>BENCHMARK-AVVIKELSE:</b> {why}</div>"
        f"<div>{_snapshot_text('Referens', mismatch.get('reference'))}</div>"
        f"<div>{_snapshot_text('Benchmark', mismatch.get('observed'))}</div>"
        f"<div>{_snapshot_text('Editor nu', current)}</div>"
        "</div>"
    )


def _seed_headword_x_from_geometry(context: dict) -> None:
    from collections import Counter

    owners = context.get("pixel_owners")
    columns = context.get("row_map", {}).get("columns") or []
    if owners is None:
        return
    store = context.setdefault("priority_headword_x_counts", {})
    for column_index, column in enumerate(columns):
        if store.get(column_index):
            continue
        left_value = (context.get("column_content_lefts") or {}).get(column_index)
        left = max(0, int(left_value if left_value is not None else column.get("crop_left", column.get("left", 0))))
        right = min(owners.width, int(column.get("crop_right", column.get("right", owners.width))))
        starts: list[int] = []
        for row_index, row in enumerate(column.get("rows") or []):
            top = max(0, int(row.get("page_top", 0)))
            bottom = min(owners.height, int(row.get("page_bottom", owners.height)))
            code = owners.row_code(row_index)
            start_x = next(
                (
                    x for x in range(left, right)
                    if any(owners.data[y * owners.width + x] == code for y in range(top, bottom))
                ),
                None,
            )
            if start_x is not None:
                starts.append(int(start_x))
        if not starts:
            continue
        center = max(starts, key=lambda value: (sum(abs(other - value) <= 2 for other in starts), value))
        members = [value for value in starts if abs(value - center) <= 2]
        exact_counts = Counter(members)
        headword_x = max(exact_counts, key=lambda value: (exact_counts[value], value))
        store[column_index] = Counter({int(headword_x): len(members)})
        context.setdefault("queue_seeded_headword_x", {})[column_index] = int(headword_x)


def _card_image(context: dict, state: dict, *, extra_left: int = 2) -> str:
    left, top, right, bottom = map(int, state["crop_box"])
    source_left = max(0, left - int(extra_left))
    strip_width = left - source_left
    owners = context.get("pixel_owners")
    if strip_width <= 0 or owners is None:
        return str(state["image"])
    owned = owners.render_owner_crop(row_index=int(state["row"]), box=(left, top, right, bottom)).convert("L")
    strip = context["page"].crop((source_left, top, left, bottom)).convert("L")
    combined = Image.new("L", (strip.width + owned.width, owned.height), 255)
    combined.paste(strip, (0, 0))
    combined.paste(owned, (strip.width, 0))
    return page_editor.fast.legacy._png_data_uri(combined)


def _fine_display_state(context: dict, state: dict, *, extra_left: int = 2) -> dict:
    left, top, right, bottom = map(int, state["crop_box"])
    source_left = max(0, left - int(extra_left))
    pad = left - source_left
    owners = context.get("pixel_owners")
    if pad <= 0 or owners is None:
        return state
    owned = owners.render_owner_crop(row_index=int(state["row"]), box=(left, top, right, bottom)).convert("L")
    strip = context["page"].crop((source_left, top, left, bottom)).convert("L")
    combined = Image.new("L", (pad + owned.width, owned.height), 255)
    combined.paste(strip, (0, 0))
    combined.paste(owned, (pad, 0))
    out = dict(state)
    out["image"] = page_editor.fast.legacy._png_data_uri(combined)
    out["crop_box"] = (source_left, top, right, bottom)
    out["crop_width"] = int(state["crop_width"]) + pad
    out["source_ink_points"] = [[int(x) + pad, int(y)] for x, y in state.get("source_ink_points") or []]
    out["point_sets"] = {
        item_id: frozenset((int(x) + pad, int(y)) for x, y in points)
        for item_id, points in (state.get("point_sets") or {}).items()
    }
    shifted_items = []
    for item in state.get("items") or []:
        shifted = dict(item)
        bbox = item.get("bbox")
        if bbox:
            shifted["bbox"] = {**bbox, "left": int(bbox["left"]) + pad, "right": int(bbox["right"]) + pad}
        shifted_items.append(shifted)
    out["items"] = shifted_items
    return out


def _url(position: Position, *, nav: str) -> str:
    return "/?" + urlencode(
        {"page": position[0], "column": position[1], "row": position[2], "nav": nav}
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Three-row SAOL pixel-array glyph editor with all-row or queue navigation."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, help="optional review queue; enables queue navigation")
    ap.add_argument("--mode", choices=("all", "queue"), help="initial navigation mode")
    ap.add_argument("--queue-index", type=int, help="1-based queue entry to start at")
    ap.add_argument("--page", type=int)
    ap.add_argument("--column", type=int, choices=(0, 1, 2))
    ap.add_argument("--row", type=int)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if (args.column is None) != (args.row is None):
        ap.error("--column and --row must be given together")
    if args.queue_index is not None and (args.page is not None or args.column is not None):
        ap.error("--queue-index cannot be combined with --page/--column/--row")

    queue_rows = _load_queue(args.queue) if args.queue else []
    queue_positions: list[Position] = [
        (int(item["page"]), int(item["column"]), int(item["row"])) for item in queue_rows
    ]
    queue_numbers = {position: index for index, position in enumerate(queue_positions, start=1)}
    queue_metadata = {
        position: item.get("benchmark_mismatch") for position, item in zip(queue_positions, queue_rows)
    }

    if args.mode == "queue" and not queue_positions:
        ap.error("--mode queue requires --queue")
    initial_nav = args.mode or ("queue" if queue_positions else "all")

    if args.queue_index is not None:
        if not queue_positions:
            ap.error("--queue-index requires --queue")
        if not 1 <= args.queue_index <= len(queue_positions):
            ap.error(f"--queue-index must be between 1 and {len(queue_positions)}")
        initial: Position = queue_positions[args.queue_index - 1]
    elif args.page is not None and args.column is not None:
        initial = (int(args.page), int(args.column), int(args.row))
    elif queue_positions:
        initial = queue_positions[0]
    else:
        ap.error("give --page/--column/--row, or provide --queue")

    contexts: dict[int, dict] = {}
    state_cache: dict[Position, dict] = {}
    models_holder = {"models": page_editor.fast.load_facit(args.facit)}
    models_lock = threading.RLock()
    message = {"text": ""}

    # Queue editor behavior: no post-match compaction.
    neighbor_raster._compact_review_state = lambda _context, state: state

    def context_for(page: int) -> dict:
        context = contexts.get(page)
        if context is None:
            context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
            _seed_headword_x_from_geometry(context)
            contexts[page] = context
        return context

    def local_positions(page: int) -> list[tuple[int, int]]:
        return list(context_for(page)["positions"])

    def validate(position: Position) -> None:
        local = (position[1], position[2])
        if local not in local_positions(position[0]):
            raise ValueError(f"row page={position[0]} column={position[1]} row={position[2]} is not present")

    validate(initial)

    def state_for(position: Position) -> dict:
        state = state_cache.get(position)
        if state is not None:
            return state
        page, column, row = position
        context = context_for(page)
        local = (column, row)
        with models_lock:
            models = models_holder["models"]
        bind_page_candidates(context, models)
        kind = classify_row_start(context, local)
        set_row_priority_hint(kind)
        state = page_editor.load_review_state_pixel_array(context, local, models)
        state["row_priority_kind"] = kind
        if state.get("fully_exact"):
            observe_row_layout(context, state)
        state["queue_card_image"] = _card_image(context, state, extra_left=2)
        if position in queue_metadata and queue_metadata[position]:
            state["benchmark_mismatch"] = queue_metadata[position]
        if position in queue_numbers:
            state["queue_position"] = (queue_numbers[position], len(queue_positions))
        state_cache[position] = state
        return state

    def all_neighbour(position: Position, delta: int) -> Position | None:
        page, column, row = position
        positions = local_positions(page)
        local = (column, row)
        index = positions.index(local) + delta
        if 0 <= index < len(positions):
            return (page, positions[index][0], positions[index][1])
        adjacent_page = page + (1 if delta > 0 else -1)
        if adjacent_page < 1:
            return None
        try:
            adjacent = local_positions(adjacent_page)
        except ValueError:
            return None
        if not adjacent:
            return None
        target = adjacent[0] if delta > 0 else adjacent[-1]
        return (adjacent_page, target[0], target[1])

    def queue_neighbour(position: Position, delta: int) -> Position | None:
        if position not in queue_numbers:
            return None
        index = queue_numbers[position] - 1 + delta
        return queue_positions[index] if 0 <= index < len(queue_positions) else None

    def neighbour(position: Position, delta: int, nav: str) -> Position | None:
        return queue_neighbour(position, delta) if nav == "queue" else all_neighbour(position, delta)

    def visible(position: Position, nav: str) -> list[Position]:
        prev = neighbour(position, -1, nav)
        nxt = neighbour(position, 1, nav)
        result = []
        if prev is not None:
            result.append(prev)
        result.append(position)
        if nxt is not None:
            result.append(nxt)
        return result

    def render(position: Position, nav: str) -> str:
        states = [state_for(item) for item in visible(position, nav)]
        active_state = state_for(position)
        display_state = _fine_display_state(context_for(position[0]), active_state, extra_left=2)
        document = page_editor.fast.ui.editor.render_html(display_state, message["text"])
        banner = _mismatch_banner(active_state)
        if banner:
            document = document.replace("<body>", "<body>" + banner, 1)

        cards = []
        for item, state in zip(visible(position, nav), states):
            active_class = " active" if item == position else ""
            exact = int(state.get("covered_pixels") or 0) == int(state.get("source_pixels") or 0)
            status = "exakt" if exact else f"{state.get('covered_pixels', 0)}/{state.get('source_pixels', 0)} px"
            cards.append(
                f'<a class="rowcard{active_class}" href="{_url(item, nav=nav)}">'
                f'<div><b>sida {item[0]} · kol {item[1]} · rad {item[2]}</b> · {html.escape(status)}</div>'
                f'<img src="{state.get("queue_card_image", state["image"])}" alt="sida {item[0]} kolumn {item[1]} rad {item[2]}">'
                f'<div class="rowtext">{html.escape(state.get("text") or "")}</div>'
                '</a>'
            )

        previous = neighbour(position, -1, nav)
        following = neighbour(position, 1, nav)
        prev_link = (
            f'<a class="navbutton" href="{_url(previous, nav=nav)}">← Föregående</a>'
            if previous else '<span class="navbutton disabled">← Föregående</span>'
        )
        next_link = (
            f'<a class="navbutton" href="{_url(following, nav=nav)}">Nästa →</a>'
            if following else '<span class="navbutton disabled">Nästa →</span>'
        )
        mode_links = []
        all_class = " modeon" if nav == "all" else ""
        mode_links.append(f'<a class="navbutton{all_class}" href="{_url(position, nav="all")}">Alla rader</a>')
        if queue_positions:
            queue_target = position if position in queue_numbers else min(
                queue_positions,
                key=lambda p: (abs(p[0] - position[0]), abs(p[1] - position[1]), abs(p[2] - position[2])),
            )
            queue_class = " modeon" if nav == "queue" else ""
            mode_links.append(
                f'<a class="navbutton{queue_class}" href="{_url(queue_target, nav="queue")}">Kö</a>'
            )
        queue_note = ""
        if nav == "queue" and position in queue_numbers:
            queue_note = f'<span>Köpost {queue_numbers[position]}/{len(queue_positions)}</span>'

        css = """
<style>
.cross-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.navbutton{display:inline-block;padding:7px 11px;border:1px solid #888;background:white;color:#171717;text-decoration:none;border-radius:4px}
.navbutton.disabled{opacity:.35}.navbutton.modeon{font-weight:700;background:#eef6ff;border-color:#1769d2}
.cross-context{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:8px;margin:10px 0 18px;max-width:1200px}
.rowcard{display:block;border:2px solid #bbb;background:white;padding:6px;color:#171717;text-decoration:none;min-width:0}.rowcard.active{border:4px solid #1769d2;padding:4px;background:#eef6ff}
.rowcard img{width:100%;height:82px;object-fit:contain;object-position:left center;image-rendering:pixelated;background:white}.rowtext{font:12px monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px}
@media(max-width:900px){.cross-context{grid-template-columns:1fr}}
</style>
"""
        nav_html = (
            '<div class="cross-nav">' + prev_link + next_link + "".join(mode_links) + queue_note + '</div>'
            + '<div class="cross-context">' + "".join(cards) + '</div>'
        )
        keyboard = f"""
<script>
document.addEventListener('keydown', e => {{
  if (e.target && ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft' && {str(previous is not None).lower()}) window.location.href = {json.dumps(_url(previous, nav=nav) if previous else '/')};
  if (e.key === 'ArrowRight' && {str(following is not None).lower()}) window.location.href = {json.dumps(_url(following, nav=nav) if following else '/')};
}});
</script>
"""
        document = document.replace("</head>", css + "</head>", 1)
        document = document.replace("<h1>", nav_html + "<h1>", 1)
        document = document.replace("</body>", keyboard + "</body>", 1)
        return document

    class Handler(BaseHTTPRequestHandler):
        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlparse(self.path).query)

        def _position(self, query: dict[str, list[str]]) -> Position:
            try:
                result = (
                    int((query.get("page") or [str(initial[0])])[0]),
                    int((query.get("column") or [str(initial[1])])[0]),
                    int((query.get("row") or [str(initial[2])])[0]),
                )
            except ValueError as exc:
                raise ValueError("page, column and row must be integers") from exc
            validate(result)
            return result

        def _nav(self, query: dict[str, list[str]]) -> str:
            nav = (query.get("nav") or [initial_nav])[0]
            if nav not in {"all", "queue"}:
                nav = initial_nav
            if nav == "queue" and not queue_positions:
                nav = "all"
            return nav

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                query = self._query()
                position = self._position(query)
                nav = self._nav(query)
                if nav == "queue" and position not in queue_numbers:
                    raise ValueError(f"row {position} is not present in queue")
                body = render(position, nav).encode("utf-8")
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
                nav = self._nav(query)
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                state = state_for(position)
                message["text"] = page_editor.fast.legacy.apply_edit(state, args.facit, form)
                with models_lock:
                    models_holder["models"] = page_editor.fast.load_facit(args.facit)
                state_cache.clear()
                location = _url(position, nav=nav)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
                location = _url(initial, nav=initial_nav)
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/" + _url(initial, nav=initial_nav)[2:]
    print(
        f"review: unified three-row editor nav={initial_nav}; start={initial}; "
        f"queue={args.queue if args.queue else '-'} ({len(queue_positions)} rows)",
        flush=True,
    )
    print(url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
