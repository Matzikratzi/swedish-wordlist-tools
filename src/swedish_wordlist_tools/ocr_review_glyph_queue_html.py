from __future__ import annotations

import argparse
import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs
from .ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT
from .ocr_glyph_review_delete import load_facit_with_typography


def load_queue(path: Path) -> list[tuple[int, int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != QUEUE_FORMAT:
        raise ValueError(
            f"unsupported queue format {payload.get('format')!r}; expected {QUEUE_FORMAT!r}"
        )
    rows: list[tuple[int, int, int]] = []
    for item in payload.get("rows") or []:
        position = (int(item["page"]), int(item["column"]), int(item["row"]))
        if position not in rows:
            rows.append(position)
    if not rows:
        raise ValueError("review queue contains no rows")
    return rows


def _queue_url(index: int) -> str:
    return "/?" + urlencode({"i": int(index)})


def _inject_queue_navigation(document: str, *, index: int, rows: list[tuple[int, int, int]]) -> str:
    page, column, row = rows[index]
    previous_url = _queue_url(index - 1) if index > 0 else None
    next_url = _queue_url(index + 1) if index + 1 < len(rows) else None

    previous = (
        f'<a class="queue-navbutton" href="{previous_url}">← Föregående kö-rad</a>'
        if previous_url
        else '<span class="queue-navbutton disabled">← Föregående kö-rad</span>'
    )
    following = (
        f'<a class="queue-navbutton" href="{next_url}">Nästa kö-rad →</a>'
        if next_url
        else '<span class="queue-navbutton disabled">Nästa kö-rad →</span>'
    )
    css = """
<style>
.queue-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.queue-navbutton{display:inline-block;padding:7px 11px;border:1px solid #888;background:white;color:#171717;text-decoration:none;border-radius:4px}
.queue-navbutton.disabled{opacity:.35}
.queue-position{font:13px monospace;margin-left:4px}
</style>
"""
    nav = (
        '<div class="queue-nav">'
        + previous
        + following
        + f'<span class="queue-position">{index + 1}/{len(rows)} · sida {page} · kolumn {column} · rad {row}</span>'
        + '</div>'
    )
    keyboard = f"""
<script>
document.addEventListener('keydown', e => {{
  if (e.target && ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft' && {str(previous_url is not None).lower()}) window.location.href = {previous_url!r};
  if (e.key === 'ArrowRight' && {str(next_url is not None).lower()}) window.location.href = {next_url!r};
}});
</script>
"""
    document = document.replace("</head>", css + "</head>", 1)
    document = document.replace("<h1>", nav + "<h1>", 1)
    return document.replace("</body>", keyboard + "</body>", 1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Review only rows listed in a SAOL glyph review queue, across multiple pages."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    rows = load_queue(args.queue)
    contexts: dict[int, dict] = {}
    states: dict[tuple[int, int, int], dict] = {}
    models_holder = {"models": load_facit_with_typography(args.facit)}
    models_lock = threading.RLock()
    cache_lock = threading.RLock()
    message = {"text": ""}

    def context_for(page: int) -> dict:
        with cache_lock:
            context = contexts.get(page)
        if context is not None:
            return context
        print(f"queue-review: laddar sida {page}", flush=True)
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        with cache_lock:
            contexts[page] = context
        return context

    def state_for(index: int) -> dict:
        page, column, row = rows[index]
        key = (page, column, row)
        with cache_lock:
            state = states.get(key)
        if state is not None:
            return state
        context = context_for(page)
        position = (column, row)
        if position not in context["positions"]:
            raise ValueError(f"queue row page {page} column {column} row {row} is not present")
        with models_lock:
            models = models_holder["models"]
        print(f"queue-review: analyserar {index + 1}/{len(rows)}: sida {page} c{column} r{row}", flush=True)
        state = page_editor.load_review_state_pixel_array(context, position, models)
        if not state.get("fully_exact"):
            records = repair_lower_row_disconnected_glyphs(context, state, models)
            if records:
                with cache_lock:
                    states.pop((page, column, row - 1), None)
                state = page_editor.load_review_state_pixel_array(context, position, models)
                state["disconnected_glyph_ownership"] = records
        with cache_lock:
            states[key] = state
        return state

    def refresh_models(reason: str) -> None:
        with models_lock:
            models_holder["models"] = load_facit_with_typography(args.facit)
        with cache_lock:
            states.clear()
        print(f"queue-review: facit omladdat ({reason}); radcache tömd", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def _index(self) -> int:
            query = parse_qs(urlparse(self.path).query)
            try:
                index = int((query.get("i") or ["0"])[0])
            except ValueError as exc:
                raise ValueError("i must be an integer") from exc
            if not 0 <= index < len(rows):
                raise ValueError(f"queue index {index} outside 0..{len(rows) - 1}")
            return index

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                index = self._index()
                state = state_for(index)
                body = page_editor.fast.ui.editor.render_html(state, message["text"])
                body = _inject_queue_navigation(body, index=index, rows=rows).encode("utf-8")
                message["text"] = ""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                self.send_error(500, str(exc))

        def do_POST(self):
            index = 0
            try:
                index = self._index()
                state = state_for(index)
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                message["text"] = page_editor.fast.legacy.apply_edit(state, args.facit, form)
                refresh_models("facit ändrat")
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
            self.send_response(303)
            self.send_header("Location", _queue_url(index))
            self.end_headers()

        def log_message(self, fmt, *values):
            print("queue-review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    print(
        f"queue-review: {len(rows)} rader från {args.queue}; piltangenter/vänster-höger går mellan kö-rader",
        flush=True,
    )
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
