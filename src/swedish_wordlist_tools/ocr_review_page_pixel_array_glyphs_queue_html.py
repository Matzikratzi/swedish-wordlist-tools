from __future__ import annotations

"""Browse a saved glyph-review queue with the page pixel-array editor."""

import argparse
import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from . import ocr_review_page_pixel_array_glyphs_html as pixel


QUEUE_FORMAT = "saol14-glyph-review-row-queue-v1"


def load_queue(path: Path) -> list[tuple[int, int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review queue must be a JSON object")
    if payload.get("format") != QUEUE_FORMAT:
        raise ValueError(
            f"unsupported review queue format {payload.get('format')!r}; "
            f"expected {QUEUE_FORMAT!r}"
        )
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("review queue has no rows list")

    rows: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for index, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            raise ValueError(f"review queue row {index} is not an object")
        try:
            position = (int(item["page"]), int(item["column"]), int(item["row"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"review queue row {index} must contain integer page/column/row"
            ) from exc
        if position[1] not in (0, 1, 2) or position[2] < 0 or position[0] < 1:
            raise ValueError(f"invalid review queue position {position}")
        if position not in seen:
            seen.add(position)
            rows.append(position)
    if not rows:
        raise ValueError("review queue is empty")
    return rows


def _queue_url(index: int) -> str:
    return "/?" + urlencode({"index": int(index)})


def _inject_queue_navigation(
    document: str,
    *,
    index: int,
    count: int,
    position: tuple[int, int, int],
    queue_path: Path,
) -> str:
    page, column, row = position
    previous_url = _queue_url(index - 1) if index > 0 else None
    next_url = _queue_url(index + 1) if index + 1 < count else None
    previous = (
        f'<a class="queue-navbutton" href="{previous_url}">← Föregående trasiga rad</a>'
        if previous_url
        else '<span class="queue-navbutton disabled">← Föregående trasiga rad</span>'
    )
    following = (
        f'<a class="queue-navbutton" href="{next_url}">Nästa trasiga rad →</a>'
        if next_url
        else '<span class="queue-navbutton disabled">Nästa trasiga rad →</span>'
    )
    css = """
<style>
.queue-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 12px}
.queue-navbutton{display:inline-block;padding:7px 11px;border:1px solid #888;background:white;color:#171717;text-decoration:none;border-radius:4px}
.queue-navbutton.disabled{opacity:.35}
.queue-position{font:13px monospace}
</style>
"""
    navigation = (
        '<div class="queue-nav">'
        + previous
        + following
        + f'<span class="queue-position">{index + 1}/{count} · sida {page} · kol {column} · rad {row}</span>'
        + f'<span>{html.escape(str(queue_path))}</span>'
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
    document = document.replace("<h1>", navigation + "<h1>", 1)
    document = document.replace("</body>", keyboard + "</body>", 1)
    return document


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Review a saved cross-page glyph queue with the page pixel-array editor."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit-v2.json"),
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    positions = load_queue(args.queue)
    page_contexts: dict[int, dict] = {}
    state_cache: dict[tuple[int, int, int], dict] = {}
    cache_lock = threading.RLock()
    models_lock = threading.RLock()
    models_holder = {"models": pixel.fast.load_facit(args.facit)}
    message = {"text": ""}

    def context_for(page: int) -> dict:
        with cache_lock:
            context = page_contexts.get(page)
        if context is not None:
            return context
        context = pixel.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        with cache_lock:
            page_contexts[page] = context
        return context

    def state_for(index: int) -> dict:
        position = positions[index]
        with cache_lock:
            cached = state_cache.get(position)
        if cached is not None:
            return cached
        page, column, row = position
        context = context_for(page)
        if (column, row) not in context["positions"]:
            raise ValueError(
                f"queue position page={page} column={column} row={row} "
                "is not present in current segmentation"
            )
        with models_lock:
            models = models_holder["models"]
        print(
            f"review: kö {index + 1}/{len(positions)}: analyserar sida {page}, "
            f"kolumn {column}, rad {row} ...",
            flush=True,
        )
        state = pixel.load_review_state_pixel_array(context, (column, row), models)
        with cache_lock:
            state_cache[position] = state
        status = "exakt" if not pixel.fast.ui.is_defective(state) else (
            f"defekt {state['covered_pixels']}/{state['source_pixels']}"
        )
        print(f"review: kö {index + 1}/{len(positions)}: {status}", flush=True)
        return state

    def refresh_models(reason: str, active: tuple[int, int, int] | None = None) -> None:
        with models_lock:
            models_holder["models"] = pixel.fast.load_facit(args.facit)
        with cache_lock:
            if active is None:
                state_cache.clear()
            else:
                state_cache.pop(active, None)
        print(f"review: facit omladdat ({reason})", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def _index(self) -> int:
            query = parse_qs(urlparse(self.path).query)
            try:
                index = int((query.get("index") or ["0"])[0])
            except ValueError as exc:
                raise ValueError("index must be an integer") from exc
            if not 0 <= index < len(positions):
                raise ValueError(f"queue index {index} is out of range")
            return index

        def do_GET(self):
            if urlparse(self.path).path != "/":
                self.send_error(404)
                return
            try:
                index = self._index()
                position = positions[index]
                state = state_for(index)
                document = pixel.fast.ui.editor.render_html(state, message["text"])
                document = _inject_queue_navigation(
                    document,
                    index=index,
                    count=len(positions),
                    position=position,
                    queue_path=args.queue,
                )
                message["text"] = ""
                body = document.encode("utf-8")
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
                position = positions[index]
                state = state_for(index)
                length = int(self.headers.get("Content-Length", "0"))
                form = parse_qs(
                    self.rfile.read(length).decode("utf-8"), keep_blank_values=True
                )
                message["text"] = pixel.fast.legacy.apply_edit(state, args.facit, form)
                refresh_models("facit ändrat", active=position)
                location = _queue_url(index)
            except Exception as exc:
                message["text"] = "FEL: " + str(exc)
                location = _queue_url(index)
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, fmt, *values):
            print("review:", fmt % values)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}{_queue_url(0)}"
    print(f"review: kö={args.queue} rader={len(positions)}", flush=True)
    print(url, flush=True)
    print(f"facit={args.facit} (vänster/höger går mellan köposterna; Ctrl-C avslutar)")
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
