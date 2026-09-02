from __future__ import annotations

import argparse
import contextlib
import io
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter

from . import ocr_review_batch_defects_html as batch
from .ocr_batch_progress_cache import BatchProgressStore, DEFAULT_CACHE_PATH
from .ocr_glyph_matcher import load_facit


class _FinishAwareServer(ThreadingHTTPServer):
    """Editor server that can be stopped by the live batch control button."""

    finish_event: threading.Event | None = None

    def service_actions(self) -> None:
        event = type(self).finish_event
        if event is not None and event.is_set():
            raise KeyboardInterrupt


def _add_finish_button(document: str, control_url: str) -> str:
    button = (
        '<div style="position:sticky;top:0;z-index:9999;padding:8px 12px;'
        'background:#fff;border-bottom:1px solid #bbb">'
        f'<a href="{control_url}" style="display:inline-block;padding:9px 15px;'
        'background:#1769aa;color:white;text-decoration:none;border-radius:5px;'
        'font-weight:700">Klar med editeringen – fortsätt</a>'
        '</div>'
    )
    needle = '<body>'
    if needle in document:
        return document.replace(needle, needle + button, 1)
    return button + document


def _launch_paused_editor(
    jsonl: Path,
    *,
    page: int,
    position: tuple[int, int],
    threshold: int,
    facit: Path,
    host: str,
    port: int,
    no_browser: bool,
) -> int:
    """Run the normal editor while the batch is completely idle.

    A tiny control server owns the explicit "done editing" button.  Clicking it
    sets an event.  The editor HTTP server observes that event from
    ``service_actions`` and exits its normal ``serve_forever`` loop.  Only then
    does the batch resume scanning with the newly loaded facit.
    """
    finish_event = threading.Event()
    control_port = port + 1

    class ControlHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            finish_event.set()
            body = (
                '<!doctype html><meta charset="utf-8">'
                '<title>Fortsätter</title>'
                '<body style="font-family:sans-serif;padding:2rem">'
                '<h2>Fortsätter batchen …</h2>'
                '<p>Nästa trasiga rad öppnas automatiskt när den hittas.</p>'
                '</body>'
            ).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _fmt, *_values):
            return

    control = ThreadingHTTPServer((host, control_port), ControlHandler)
    control_thread = threading.Thread(target=control.serve_forever, name='ocr-batch-control', daemon=True)
    control_thread.start()

    fast = batch.boundary.fast
    original_server = fast.ThreadingHTTPServer
    original_render = fast.ui.render_five_row_html
    control_url = f'http://{host}:{control_port}/finish'

    def render_with_finish(*args, **kwargs):
        return _add_finish_button(original_render(*args, **kwargs), control_url)

    _FinishAwareServer.finish_event = finish_event
    fast.ThreadingHTTPServer = _FinishAwareServer
    fast.ui.render_five_row_html = render_with_finish
    try:
        print(
            f'batch: FEL page={page} col={position[0]} row={position[1]}; '
            'batchen står nu helt still tills du klickar "Klar med editeringen – fortsätt"',
            flush=True,
        )
        return batch.launch_editor(
            jsonl,
            page=page,
            position=position,
            threshold=threshold,
            facit=facit,
            host=host,
            port=port,
            no_browser=no_browser,
        )
    finally:
        fast.ui.render_five_row_html = original_render
        fast.ThreadingHTTPServer = original_server
        _FinishAwareServer.finish_event = None
        control.shutdown()
        control.server_close()
        control_thread.join(timeout=2.0)


def _quiet_scan_page(*args, **kwargs) -> dict:
    """Keep boundary/row diagnostics out of the normal live terminal."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return batch.scan_page(*args, **kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Sequential OCR batch review: scan until a defect, then stop completely while editing.'
    )
    ap.add_argument('jsonl', type=Path)
    ap.add_argument('--pages', required=True)
    ap.add_argument('--threshold', type=int, default=210)
    ap.add_argument('--facit', type=Path, default=Path('glyphs/saol14-manual-glyph-facit.json'))
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8766)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--progress-cache', type=Path, default=DEFAULT_CACHE_PATH)
    ap.add_argument('--reset-progress', action='store_true')
    args = ap.parse_args()

    try:
        pages = batch.parse_pages(args.pages)
    except ValueError as exc:
        ap.error(str(exc))

    progress_store = BatchProgressStore(args.progress_cache)
    if args.reset_progress:
        progress_store.clear()
        print(f'batch: rensade progress-cache {args.progress_cache}', flush=True)

    started = perf_counter()
    print(
        f'batch: sekventiellt live-läge för sidor {pages}; '
        'ingen bakgrundsprocessning medan editorn är öppen',
        flush=True,
    )

    for page in pages:
        while True:
            models = load_facit(args.facit)
            report = _quiet_scan_page(
                args.jsonl,
                page,
                models,
                threshold=args.threshold,
                stop_after_first_defect=True,
                progress_store=progress_store,
            )

            if not report['defects']:
                suffix = ' (cachad)' if report.get('cached_complete') else ''
                print(f'batch: sida {page} klar{suffix}', flush=True)
                break

            first = report['defects'][0]
            position = (int(first['column']), int(first['row']))
            print(
                f"batch: FEL page={page} col={position[0]} row={position[1]} "
                f"unknown={first['unknown_pixels']} text={first['text']!r}",
                flush=True,
            )
            _launch_paused_editor(
                args.jsonl,
                page=page,
                position=position,
                threshold=args.threshold,
                facit=args.facit,
                host=args.host,
                port=args.port,
                no_browser=args.no_browser,
            )
            print('batch: fortsätter med aktuellt facit', flush=True)

    print(
        f'batch: alla valda sidor klara; elapsed={perf_counter() - started:.1f}s',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
