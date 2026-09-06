from __future__ import annotations

"""Open the page pixel-array glyph editor on only rows listed in a review queue."""

import argparse
import html
import json
import sys
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_find_unreviewed_glyph_rows import QUEUE_FORMAT


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
    if not mismatch:
        return ""
    current = {
        "text": str(state.get("text") or ""),
        "source_pixels": int(state.get("source_pixels") or 0),
        "covered_pixels": int(state.get("covered_pixels") or 0),
        "exact": bool(state.get("fully_exact", False)),
    }
    why = html.escape(str(mismatch.get("why") or "okänd referensavvikelse"))
    return (
        "<div style=\"margin:8px 0 14px;padding:10px 12px;border:2px solid #b66;"
        "background:#fff5f0;font:14px/1.45 sans-serif\">"
        f"<div><b>BENCHMARK-AVVIKELSE:</b> {why}</div>"
        f"<div>{_snapshot_text('Referens', mismatch.get('reference'))}</div>"
        f"<div>{_snapshot_text('Benchmark', mismatch.get('observed'))}</div>"
        f"<div>{_snapshot_text('Editor nu', current)}</div>"
        "</div>"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Review only queued SAOL glyph rows with the page pixel-array editor."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument(
        "--page",
        type=int,
        help="queue page to review; defaults to the first page present in the queue",
    )
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--facit",
        type=Path,
        default=Path("glyphs/saol14-manual-glyph-facit.json"),
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    rows = _load_queue(args.queue)
    pages = sorted({int(row["page"]) for row in rows})
    selected_page = int(args.page) if args.page is not None else pages[0]
    selected_rows = [row for row in rows if int(row["page"]) == selected_page]
    selected = [
        (int(row["column"]), int(row["row"]))
        for row in selected_rows
    ]
    # Preserve queue order but suppress accidental duplicate coordinates.
    selected = list(dict.fromkeys(selected))
    if not selected:
        raise ValueError(
            f"queue has no rows on page {selected_page}; available pages: {pages}"
        )
    queued = set(selected)
    metadata = {
        (int(row["column"]), int(row["row"])): row.get("benchmark_mismatch")
        for row in selected_rows
    }

    original_build = page_editor.build_page_context_pixel_array
    original_loader = page_editor.load_review_state_pixel_array
    original_render = page_editor.fast.ui.editor.render_html
    original_argv = sys.argv

    def build_queued_page_context(jsonl: Path, page_number: int, threshold: int = 210):
        context = original_build(jsonl, page_number, threshold)
        available = set(context["positions"])
        missing = [position for position in selected if position not in available]
        if missing:
            raise ValueError(
                f"queued rows are not present on page {page_number}: {missing}"
            )
        # Keep physical page order.  All editor navigation now sees only queued rows.
        context["positions"] = [
            position for position in context["positions"] if position in queued
        ]
        print(
            f"review: queue {args.queue}: page {page_number}: "
            f"visar endast {len(context['positions'])} kö-rader",
            flush=True,
        )
        return context

    def load_with_mismatch(context, position, models):
        state = original_loader(context, position, models)
        mismatch = metadata.get(position)
        if mismatch:
            state["benchmark_mismatch"] = mismatch
        return state

    def render_with_mismatch(state, message=""):
        document = original_render(state, message)
        banner = _mismatch_banner(state)
        if not banner:
            return document
        if "<body>" in document:
            return document.replace("<body>", "<body>" + banner, 1)
        return banner + document

    page_editor.build_page_context_pixel_array = build_queued_page_context
    page_editor.load_review_state_pixel_array = load_with_mismatch
    page_editor.fast.ui.editor.render_html = render_with_mismatch
    argv = [
        original_argv[0],
        str(args.jsonl),
        "--page",
        str(selected_page),
        "--column",
        str(selected[0][0]),
        "--row",
        str(selected[0][1]),
        "--threshold",
        str(args.threshold),
        "--facit",
        str(args.facit),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.no_browser:
        argv.append("--no-browser")
    sys.argv = argv
    try:
        print(
            f"review: queue pages={pages}; active page={selected_page}; rows={len(selected)}",
            flush=True,
        )
        return page_editor.main()
    finally:
        sys.argv = original_argv
        page_editor.build_page_context_pixel_array = original_build
        page_editor.load_review_state_pixel_array = original_loader
        page_editor.fast.ui.editor.render_html = original_render


if __name__ == "__main__":
    raise SystemExit(main())
