from __future__ import annotations

"""Run sequential raw-page OCR through every column until its natural end."""

import argparse
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from time import perf_counter

from . import ocr_raw_page_baseline_debug as debug


def _write(handle, event: dict) -> None:
    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _captured(func, *args):
    buf = StringIO()
    with redirect_stdout(buf):
        result = func(*args)
    return result, [line for line in buf.getvalue().splitlines() if line]


def _is_natural_end(exc: RuntimeError) -> bool:
    return "no start ink in y=" in str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR every row in every column of one SAOL page.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--trace-output", type=Path, default=None)
    args = ap.parse_args()

    started = perf_counter()
    setup_started = perf_counter()
    models, load_diag = _captured(debug.load_facit_with_typography, args.facit)
    context, setup_diag = _captured(
        debug.page_editor.build_page_context_pixel_array,
        args.jsonl, args.page, args.threshold,
    )
    context["quiet_successful_ownership"] = True
    _unused, bind_diag = _captured(debug.cached.bind_page_candidates, context, models)
    layout_diag = []
    if args.page == 1:
        _unused, layout_diag = _captured(
            debug._install_page1_raw_layout, context, args.jsonl, args.threshold
        )
    setup_time = perf_counter() - setup_started

    raw_layout = context.get("raw_page_column_layout") or {}
    if raw_layout:
        columns = sorted(int(c) for c in raw_layout)
    else:
        columns = sorted(int(c) for c in context["row_map"]["columns"])

    trace_output = args.trace_output or Path(f"/tmp/saol14-page{args.page}-raw-baselines.jsonl")
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    ocr_time = 0.0
    total_rows = 0
    failed = None

    with trace_output.open("w", encoding="utf-8") as trace:
        _write(trace, {
            "type": "meta", "version": 3, "mode": "all", "page": args.page,
            "source_jsonl": str(args.jsonl.resolve()), "facit": str(args.facit.resolve()),
            "threshold": args.threshold, "columns": columns,
        })
        for phase, lines in (("load-facit", load_diag), ("page-setup", setup_diag),
                             ("bind-candidates", bind_diag), ("layout", layout_diag)):
            for text in lines:
                _write(trace, {"type": "diagnostic", "phase": phase, "text": text})

        for column in columns:
            left, right = debug._column_bounds_for_debug(context, column)
            _write(trace, {"type": "column", "column": column, "left": left, "right": right})
            row = 0
            while True:
                row_started = perf_counter()
                try:
                    cache, diagnostics = _captured(
                        debug.sequential.ensure_row_cached, context, column, row, models
                    )
                except RuntimeError as exc:
                    ocr_time += perf_counter() - row_started
                    reason = str(exc)
                    natural = _is_natural_end(exc)
                    _write(trace, {
                        "type": "column_end" if natural else "stop",
                        "column": column, "row": row, "reason": reason,
                    })
                    if natural:
                        print(f"raw-page-column: column={column} rows={row} complete")
                        break
                    failed = (column, row, reason)
                    print(f"raw-page-stop: column={column} row={row:03d} reason={reason}")
                    break
                ocr_time += perf_counter() - row_started
                for text in diagnostics:
                    _write(trace, {"type": "diagnostic", "phase": "row-discovery", "column": column, "row": row, "text": text})

                entry = cache[row]
                initial_border = context["raw_page_initial_border_cache"][column]
                probe = debug._row_start_probe_pixel(context, column, cache, row)
                upper_border = initial_border if row == 0 else int(cache[row - 1].border)
                _write(trace, {
                    "type": "row", "column": column, "row": entry.row,
                    "initial_border": int(initial_border), "upper_border": int(upper_border),
                    "debug_top": entry.debug_top, "start_x": entry.start_x,
                    "baseline": entry.baseline, "border": entry.border,
                    "matched_glyphs": entry.matched_glyphs,
                    "matched_pixels": entry.matched_pixels,
                    "matched_right": entry.matched_right,
                    "probe_x": probe[0] if probe else None,
                    "probe_y": probe[1] if probe else None,
                })
                row += 1
                total_rows += 1

            if failed is not None:
                break

        _write(trace, {
            "type": "summary", "rows": total_rows,
            "failed_column": failed[0] if failed else None,
            "failed_row": failed[1] if failed else None,
            "failed_reason": failed[2] if failed else None,
        })

    elapsed = perf_counter() - started
    print(f"raw-page-debug-trace: {trace_output}")
    print(f"raw-page-all: page={args.page} columns={len(columns)} rows={total_rows}")
    print(
        f"raw-page-timing-summary: ocr={ocr_time:.6f}s setup={setup_time:.6f}s "
        f"total={elapsed:.6f}s render=separate-process"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
