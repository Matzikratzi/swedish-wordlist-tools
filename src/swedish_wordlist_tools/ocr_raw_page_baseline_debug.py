from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery.

The OCR process deliberately does not render debug images.  It writes a small
JSONL trace containing the geometry needed by ``ocr_raw_page_baseline_render``.
That renderer can be run afterwards without repeating OCR.

Verbose diagnostics produced by the experimental scanner are captured and
stored in that trace as ``diagnostic`` events instead of flooding stdout.
Timing lines remain visible when this module is run through the timing wrapper.
"""

import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

from . import ocr_page_cached_fast_path as cached
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_sequential_raw_page_rows_headwordfast as sequential
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_page1_layout_debug import _load_thresholded_page, detect_page1_layout_details


def _install_page1_raw_layout(context: dict, jsonl: Path, threshold: int) -> None:
    """Install absolute raw-pixel column bounds and row-0 search starts for page 1."""
    layout_page = _load_thresholded_page(jsonl, 1, threshold)
    layout = detect_page1_layout_details(layout_page)
    context["raw_page_column_layout"] = {
        column.index + 1: {
            "left": column.left,
            "right": column.right,
            "row0_top": row0_top,
            "bottom": context["pixel_owners"].height,
        }
        for column, row0_top in zip(layout.columns, layout.row0_tops)
    }
    context["raw_page_layout_source"] = "page1-raw-pixels"


def _column_bounds_for_debug(context: dict, column: int) -> tuple[int, int]:
    raw_layout = context.get("raw_page_column_layout") or {}
    if column in raw_layout:
        entry = raw_layout[column]
        return int(entry["left"]), int(entry["right"])
    entry = context["row_map"]["columns"][column]
    return (
        int(entry.get("crop_left", entry.get("left", 0))),
        int(entry.get("crop_right", entry.get("right", context["pixel_owners"].width))),
    )


def _row_start_probe_pixel(context: dict, column: int, cache, row: int) -> tuple[int, int] | None:
    """Reproduce the scanner's x-first start probe and return its source pixel."""
    initial_border = (context.get("raw_page_initial_border_cache") or {}).get(column)
    if initial_border is None:
        return None

    if row == 0:
        search_from = int(initial_border) + 1
    else:
        search_from = int(cache[row - 1].border)

    owners = context["pixel_owners"]
    left, right = _column_bounds_for_debug(context, column)
    x1 = min(right, left + sequential.FIRST_TEXT_SEARCH_WIDTH)
    y1 = min(owners.height, search_from + sequential.START_SEARCH_HEIGHT)
    data = owners.data
    for x in range(left, x1):
        for y in range(search_from, y1):
            if data[y * owners.width + x] != 0:
                return x, y
    return None


def _write_event(handle, event: dict) -> None:
    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
    handle.write("\n")
    handle.flush()


def _captured_call(func, *args, **kwargs):
    """Run a noisy helper and return its result plus captured output lines.

    Timing lines are copied back to stdout so the timing wrapper stays useful;
    every other line is intended for the JSONL trace.
    """
    buffer = StringIO()
    with redirect_stdout(buffer):
        result = func(*args, **kwargs)
    diagnostics = []
    for line in buffer.getvalue().splitlines():
        if line.startswith("raw-page-timing:"):
            print(line)
        elif line:
            diagnostics.append(line)
    return result, diagnostics


def _write_diagnostics(trace, diagnostics, *, phase: str, row: int | None = None) -> None:
    for text in diagnostics:
        event = {"type": "diagnostic", "phase": phase, "text": text}
        if row is not None:
            event["row"] = row
        _write_event(trace, event)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Walk a SAOL column from row 0, cache rows and write baseline/border "
            "geometry to JSONL. Rendering is done separately afterwards."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument(
        "--row",
        type=int,
        required=True,
        help="target discovered row; rows 0..N are scanned sequentially",
    )
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--trace-output",
        type=Path,
        default=None,
        help="JSONL debug trace; default /tmp/saol14-pageN-cM-raw-baselines.jsonl",
    )
    args = ap.parse_args()

    trace_output = args.trace_output or Path(
        f"/tmp/saol14-page{args.page}-c{args.column}-raw-baselines.jsonl"
    )
    trace_output.parent.mkdir(parents=True, exist_ok=True)

    models, load_diagnostics = _captured_call(load_facit_with_typography, args.facit)
    context, setup_diagnostics = _captured_call(
        page_editor.build_page_context_pixel_array,
        args.jsonl,
        args.page,
        args.threshold,
    )
    context["quiet_successful_ownership"] = True
    _bound, bind_diagnostics = _captured_call(cached.bind_page_candidates, context, models)

    layout_diagnostics = []
    if args.page == 1:
        _unused, layout_diagnostics = _captured_call(
            _install_page1_raw_layout, context, args.jsonl, args.threshold
        )

    left, right = _column_bounds_for_debug(context, args.column)
    completed = []
    stopped_row: int | None = None
    stopped_reason: str | None = None

    with trace_output.open("w", encoding="utf-8") as trace:
        _write_event(
            trace,
            {
                "type": "meta",
                "version": 2,
                "source_jsonl": str(args.jsonl.resolve()),
                "facit": str(args.facit.resolve()),
                "page": args.page,
                "column": args.column,
                "target_row": args.row,
                "threshold": args.threshold,
                "left": left,
                "right": right,
                "layout_source": context.get("raw_page_layout_source"),
            },
        )
        _write_diagnostics(trace, load_diagnostics, phase="load-facit")
        _write_diagnostics(trace, setup_diagnostics, phase="page-setup")
        _write_diagnostics(trace, bind_diagnostics, phase="bind-candidates")
        _write_diagnostics(trace, layout_diagnostics, phase="layout")

        if args.page == 1:
            raw_column = context["raw_page_column_layout"][args.column]
            _write_event(
                trace,
                {
                    "type": "layout",
                    "source": context["raw_page_layout_source"],
                    "column": args.column,
                    "left": raw_column["left"],
                    "right": raw_column["right"],
                    "row0_search_from": raw_column["row0_top"],
                    "page1_start_probe": "bold:a,á,à,A,Á,À",
                    "geometry": "initial-border-then-previous-border",
                    "row_start": "x-first upper-boundary..+14",
                    "homonym": "same-baseline-allow-x-overlap",
                },
            )

        for row_index in range(args.row + 1):
            try:
                cache, row_diagnostics = _captured_call(
                    sequential.ensure_row_cached,
                    context,
                    args.column,
                    row_index,
                    models,
                )
                _write_diagnostics(
                    trace, row_diagnostics, phase="row-discovery", row=row_index
                )
            except RuntimeError as exc:
                stopped_row = row_index
                stopped_reason = str(exc)
                _write_event(
                    trace,
                    {
                        "type": "stop",
                        "row": row_index,
                        "reason": stopped_reason,
                    },
                )
                print(f"raw-page-stop: row={row_index:03d} reason={exc}")
                break

            entry = cache[row_index]
            completed = list(cache)
            initial_border = context["raw_page_initial_border_cache"][args.column]
            probe = _row_start_probe_pixel(context, args.column, cache, row_index)
            upper_border = (
                initial_border if row_index == 0 else int(cache[row_index - 1].border)
            )
            event = {
                "type": "row",
                "row": entry.row,
                "initial_border": int(initial_border),
                "upper_border": int(upper_border),
                "debug_top": entry.debug_top,
                "start_x": entry.start_x,
                "baseline": entry.baseline,
                "border": entry.border,
                "matched_glyphs": entry.matched_glyphs,
                "matched_pixels": entry.matched_pixels,
                "matched_right": entry.matched_right,
                "probe_x": probe[0] if probe is not None else None,
                "probe_y": probe[1] if probe is not None else None,
            }
            _write_event(trace, event)

        _write_event(
            trace,
            {
                "type": "summary",
                "cached_rows": len(completed),
                "stopped_row": stopped_row,
                "stopped_reason": stopped_reason,
            },
        )

    print(f"raw-page-debug-trace: {trace_output}")
    if stopped_row is None:
        print(
            f"raw-page-sequential: page={args.page} column={args.column} "
            f"target_row={args.row} cached_rows={len(completed)}"
        )
    else:
        print(
            f"raw-page-sequential: page={args.page} column={args.column} "
            f"target_row={args.row} cached_rows={len(completed)} stopped_row={stopped_row}"
        )
        if stopped_reason:
            print(f"raw-page-sequential-stop-reason: {stopped_reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
