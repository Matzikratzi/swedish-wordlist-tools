from __future__ import annotations

"""Run sequential raw-page OCR through every column until its natural end."""

import argparse
import json
import re
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from time import perf_counter

from . import ocr_raw_page_baseline_debug as debug


_SLOW_ROW_SECONDS = 0.30
_PROGRESS_EVERY = 10
_RACE_RE = re.compile(r"raw-page-baseline-race: .*?rounds=(\d+)\s*(.*)$")
_HEADWORD_RE = re.compile(r"raw-page-headword-leftedge-probe: models=(\d+) proposals=(\d+) full_tests=(\d+)")


def _write(handle, event: dict) -> None:
    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _captured(func, *args):
    buf = StringIO()
    with redirect_stdout(buf):
        result = func(*args)
    return result, [line for line in buf.getvalue().splitlines() if line]


def _is_natural_end(exc: RuntimeError) -> bool:
    return "no start ink in y=" in str(exc)


def _cost_profile(diagnostics: list[str]) -> dict[str, int]:
    """Compress verbose scanner diagnostics into cheap per-row counters."""
    races = 0
    race_rounds = 0
    race_rounds_max = 0
    race_candidates = 0
    cache_hits = 0
    headword_models = 0
    headword_proposals = 0
    headword_full_tests = 0
    small_run_rejects = 0

    for line in diagnostics:
        match = _RACE_RE.match(line)
        if match:
            rounds = int(match.group(1))
            tail = match.group(2)
            races += 1
            race_rounds += rounds
            race_rounds_max = max(race_rounds_max, rounds)
            race_candidates += tail.count("b=")
            continue
        match = _HEADWORD_RE.match(line)
        if match:
            headword_models += int(match.group(1))
            headword_proposals += int(match.group(2))
            headword_full_tests += int(match.group(3))
            continue
        if line.startswith("raw-page-walk-cache-hit:"):
            cache_hits += 1
        elif line.startswith("raw-page-baseline-reject-small-run:"):
            small_run_rejects += 1

    return {
        "races": races,
        "race_rounds": race_rounds,
        "race_rounds_max": race_rounds_max,
        "race_candidates": race_candidates,
        "cache_hits": cache_hits,
        "headword_models": headword_models,
        "headword_proposals": headword_proposals,
        "headword_full_tests": headword_full_tests,
        "small_run_rejects": small_run_rejects,
    }


def _print_progress(*, column: int, row: int, row_seconds: float, total_rows: int, entry, slow: bool, profile: dict[str, int]) -> None:
    kind = "slow" if slow else "progress"
    print(
        f"raw-page-{kind}: column={column} row={row:03d} "
        f"time={row_seconds:.3f}s total_rows={total_rows} "
        f"baseline={entry.baseline} border={entry.border} "
        f"glyphs={entry.matched_glyphs} pixels={entry.matched_pixels} "
        f"races={profile['races']} candidates={profile['race_candidates']} "
        f"rounds={profile['race_rounds']} max_rounds={profile['race_rounds_max']} "
        f"cache_hits={profile['cache_hits']} headword_tests={profile['headword_full_tests']} "
        f"small_rejects={profile['small_run_rejects']}"
    )


def _disable_duplicate_glyph_trace() -> None:
    """Use the real race walker directly in full-page mode.

    The headword-fast experiment normally wraps every race step with a second
    candidate search solely to print which glyph will be chosen.  That is useful
    in single-row diagnostics but wasteful when scanning a whole page.
    """
    sequential = debug.sequential
    previous = getattr(sequential, "_previous", None)
    original = getattr(sequential, "_ORIGINAL_RACE_ADVANCE_ONE", None)
    if previous is not None and original is not None:
        previous._advance_one = original


def main() -> int:
    ap = argparse.ArgumentParser(description="OCR every row in every column of one SAOL page.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--trace-output", type=Path, default=None)
    args = ap.parse_args()

    _disable_duplicate_glyph_trace()

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
        columns_data = context["row_map"]["columns"]
        columns = list(range(1, len(columns_data) + 1)) if isinstance(columns_data, list) else sorted(int(c) for c in columns_data)

    trace_output = args.trace_output or Path(f"/tmp/saol14-page{args.page}-raw-baselines.jsonl")
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    ocr_time = 0.0
    total_rows = 0
    failed = None

    with trace_output.open("w", encoding="utf-8") as trace:
        _write(trace, {
            "type": "meta", "version": 5, "mode": "all", "page": args.page,
            "source_jsonl": str(args.jsonl.resolve()), "facit": str(args.facit.resolve()),
            "threshold": args.threshold, "columns": columns,
            "progress_every": _PROGRESS_EVERY, "slow_row_seconds": _SLOW_ROW_SECONDS,
            "duplicate_glyph_trace": False,
        })
        for phase, lines in (("load-facit", load_diag), ("page-setup", setup_diag),
                             ("bind-candidates", bind_diag), ("layout", layout_diag)):
            for text in lines:
                _write(trace, {"type": "diagnostic", "phase": phase, "text": text})

        for column in columns:
            left, right = debug._column_bounds_for_debug(context, column)
            raw_column = raw_layout.get(column) if raw_layout else None
            column_bottom = int(raw_column["bottom"]) if raw_column is not None else None
            _write(trace, {
                "type": "column", "column": column, "left": left, "right": right,
                "bottom": column_bottom,
            })
            row = 0
            while True:
                cache_now = (context.get("raw_page_row_boundary_cache") or {}).get(column) or []
                if column_bottom is not None and cache_now and cache_now[-1].border >= column_bottom:
                    _write(trace, {
                        "type": "column_end", "column": column, "row": row,
                        "reason": "known column bottom reached", "bottom": column_bottom,
                    })
                    print(f"raw-page-column: column={column} rows={row} complete bottom={column_bottom}")
                    break

                row_started = perf_counter()
                try:
                    cache, diagnostics = _captured(
                        debug.sequential.ensure_row_cached, context, column, row, models
                    )
                except RuntimeError as exc:
                    row_seconds = perf_counter() - row_started
                    ocr_time += row_seconds
                    reason = str(exc)
                    natural = _is_natural_end(exc)
                    _write(trace, {
                        "type": "column_end" if natural else "stop",
                        "column": column, "row": row, "reason": reason,
                        "seconds": row_seconds,
                    })
                    if natural:
                        print(f"raw-page-column: column={column} rows={row} complete")
                        break
                    failed = (column, row, reason)
                    print(f"raw-page-stop: column={column} row={row:03d} time={row_seconds:.3f}s reason={reason}")
                    break
                row_seconds = perf_counter() - row_started
                ocr_time += row_seconds
                profile = _cost_profile(diagnostics)
                for text in diagnostics:
                    _write(trace, {"type": "diagnostic", "phase": "row-discovery", "column": column, "row": row, "text": text})

                entry = cache[row]
                initial_border = context["raw_page_initial_border_cache"][column]
                probe = debug._row_start_probe_pixel(context, column, cache, row)
                upper_border = initial_border if row == 0 else int(cache[row - 1].border)
                _write(trace, {
                    "type": "row", "column": column, "row": entry.row,
                    "seconds": row_seconds,
                    "cost": profile,
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

                slow = row_seconds >= _SLOW_ROW_SECONDS
                periodic = total_rows % _PROGRESS_EVERY == 0
                if slow or periodic:
                    _print_progress(
                        column=column,
                        row=entry.row,
                        row_seconds=row_seconds,
                        total_rows=total_rows,
                        entry=entry,
                        slow=slow,
                        profile=profile,
                    )

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
