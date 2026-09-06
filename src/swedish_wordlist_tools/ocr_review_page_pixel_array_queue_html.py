from __future__ import annotations

"""Open the page pixel-array glyph editor on only rows listed in a review queue."""

import argparse
import html
import json
import sys
from pathlib import Path

from PIL import Image

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
    queue_position = state.get("queue_position")
    queue_line = ""
    if queue_position:
        queue_line = (
            f"<div><b>KÖPOST:</b> {int(queue_position[0])}/{int(queue_position[1])}</div>"
        )
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
        "<div style=\"margin:8px 0 14px;padding:10px 12px;border:2px solid #b66;"
        "background:#fff5f0;font:14px/1.45 sans-serif\">"
        f"{queue_line}"
        f"<div><b>BENCHMARK-AVVIKELSE:</b> {why}</div>"
        f"<div>{_snapshot_text('Referens', mismatch.get('reference'))}</div>"
        f"<div>{_snapshot_text('Benchmark', mismatch.get('observed'))}</div>"
        f"<div>{_snapshot_text('Editor nu', current)}</div>"
        "</div>"
    )


def _centered_three_positions(positions, current, size=3):
    """Show previous/current/next so the active queued row is the middle card."""
    if current not in positions:
        raise ValueError(f"row {current} is not present on page")
    index = positions.index(current)
    if len(positions) <= 3:
        return list(positions)
    start = max(0, min(index - 1, len(positions) - 3))
    return positions[start : start + 3]


def _queue_card_image(context: dict, state: dict, *, extra_left: int = 2) -> str:
    """Prepend raw source columns to the large clickable queue-row image.

    The ordinary state image remains the owned OCR crop.  For queue review we
    want exactly two source columns immediately *before* that crop so a stray
    or forgotten pixel cannot be hidden merely because it was never assigned
    to the row.  Keeping the strip separate also guarantees that the two new
    columns are visibly at the left edge rather than changing OCR geometry.
    """
    left, top, right, bottom = map(int, state["crop_box"])
    source_left = max(0, left - int(extra_left))
    strip_width = left - source_left
    owners = context.get("pixel_owners")
    if strip_width <= 0 or owners is None:
        return str(state["image"])

    owned = owners.render_owner_crop(
        row_index=int(state["row"]), box=(left, top, right, bottom)
    ).convert("L")
    strip = context["page"].crop((source_left, top, left, bottom)).convert("L")
    combined = Image.new("L", (strip.width + owned.width, owned.height), 255)
    combined.paste(strip, (0, 0))
    combined.paste(owned, (strip.width, 0))
    return page_editor.fast.legacy._png_data_uri(combined)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Review only queued SAOL glyph rows with the page pixel-array editor."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument(
        "--queue-index",
        type=int,
        help="1-based queue entry to start at; selects its page automatically",
    )
    ap.add_argument(
        "--page",
        type=int,
        help="queue page to review; defaults to the first page present in the queue",
    )
    ap.add_argument("--column", type=int, help="column of queued row to start at")
    ap.add_argument("--row", type=int, help="row of queued row to start at")
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
    pages = sorted({int(item["page"]) for item in rows})

    if (args.column is None) != (args.row is None):
        ap.error("--column and --row must be given together")
    if args.queue_index is not None and (args.page is not None or args.column is not None):
        ap.error("--queue-index cannot be combined with --page/--column/--row")

    start_item = None
    if args.queue_index is not None:
        if not 1 <= args.queue_index <= len(rows):
            ap.error(f"--queue-index must be between 1 and {len(rows)}")
        start_item = rows[args.queue_index - 1]
        selected_page = int(start_item["page"])
    else:
        selected_page = int(args.page) if args.page is not None else pages[0]

    selected_rows = [item for item in rows if int(item["page"]) == selected_page]
    selected = [(int(item["column"]), int(item["row"])) for item in selected_rows]
    selected = list(dict.fromkeys(selected))
    if not selected:
        raise ValueError(
            f"queue has no rows on page {selected_page}; available pages: {pages}"
        )

    if start_item is not None:
        start_position = (int(start_item["column"]), int(start_item["row"]))
    elif args.column is not None:
        start_position = (int(args.column), int(args.row))
        if start_position not in selected:
            raise ValueError(
                f"requested start row page={selected_page} column={args.column} row={args.row} "
                "is not present in the review queue"
            )
    else:
        start_position = selected[0]

    queued = set(selected)
    metadata = {
        (int(item["column"]), int(item["row"])): item.get("benchmark_mismatch")
        for item in selected_rows
    }
    queue_numbers = {
        (int(item["page"]), int(item["column"]), int(item["row"])): index
        for index, item in enumerate(rows, start=1)
    }

    original_build = page_editor.build_page_context_pixel_array
    original_loader = page_editor.load_review_state_pixel_array
    original_render = page_editor.fast.ui.editor.render_html
    original_packet_positions = page_editor.fast.ui.packet_positions
    original_packet_render = page_editor.fast.ui.render_five_row_html
    original_argv = sys.argv
    context_holder: dict[str, dict] = {}

    def build_queued_page_context(jsonl: Path, page_number: int, threshold: int = 210):
        context = original_build(jsonl, page_number, threshold)
        context_holder["context"] = context
        available = set(context["positions"])
        missing = [position for position in selected if position not in available]
        if missing:
            raise ValueError(
                f"queued rows are not present on page {page_number}: {missing}"
            )
        context["positions"] = [
            position for position in context["positions"] if position in queued
        ]
        print(
            f"review: queue {args.queue}: page {page_number}: "
            f"visar endast {len(context['positions'])} kö-rader; "
            "+2 källpixelkolumner i vänsterkant på de stora radkorten",
            flush=True,
        )
        return context

    def load_with_mismatch(context, position, models):
        state = original_loader(context, position, models)
        state["queue_card_image"] = _queue_card_image(context, state, extra_left=2)
        mismatch = metadata.get(position)
        if mismatch:
            state["benchmark_mismatch"] = mismatch
        queue_number = queue_numbers.get((selected_page, position[0], position[1]))
        if queue_number is not None:
            state["queue_position"] = (queue_number, len(rows))
        return state

    def render_with_mismatch(state, message=""):
        document = original_render(state, message)
        banner = _mismatch_banner(state)
        if not banner:
            return document
        if "<body>" in document:
            return document.replace("<body>", "<body>" + banner, 1)
        return banner + document

    def render_queue_packet(states, active_position, all_positions, message="", *, mode="all", anchor=None):
        document = original_packet_render(
            states, active_position, all_positions, message, mode=mode, anchor=anchor
        )
        for state in states:
            position = (int(state["column"]), int(state["row"]))
            old = (
                f'<img src="{state["image"]}" '
                f'alt="kolumn {position[0]}, rad {position[1]}">'
            )
            new = (
                f'<img src="{state.get("queue_card_image", state["image"])}" '
                f'alt="kolumn {position[0]}, rad {position[1]}">'
            )
            if old not in document:
                raise ValueError(f"could not find queue row-card image for {position}")
            document = document.replace(old, new, 1)
        return document

    page_editor.build_page_context_pixel_array = build_queued_page_context
    page_editor.load_review_state_pixel_array = load_with_mismatch
    page_editor.fast.ui.editor.render_html = render_with_mismatch
    page_editor.fast.ui.packet_positions = _centered_three_positions
    page_editor.fast.ui.render_five_row_html = render_queue_packet
    argv = [
        original_argv[0],
        str(args.jsonl),
        "--page", str(selected_page),
        "--column", str(start_position[0]),
        "--row", str(start_position[1]),
        "--threshold", str(args.threshold),
        "--facit", str(args.facit),
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.no_browser:
        argv.append("--no-browser")
    sys.argv = argv
    try:
        queue_number = queue_numbers.get((selected_page, start_position[0], start_position[1]))
        print(
            f"review: queue pages={pages}; active page={selected_page}; rows={len(selected)}; "
            f"start={start_position}; queue-index={queue_number}/{len(rows)}",
            flush=True,
        )
        return page_editor.main()
    finally:
        sys.argv = original_argv
        page_editor.build_page_context_pixel_array = original_build
        page_editor.load_review_state_pixel_array = original_loader
        page_editor.fast.ui.editor.render_html = original_render
        page_editor.fast.ui.packet_positions = original_packet_positions
        page_editor.fast.ui.render_five_row_html = original_packet_render


if __name__ == "__main__":
    raise SystemExit(main())
