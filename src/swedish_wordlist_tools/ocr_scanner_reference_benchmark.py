from __future__ import annotations

"""Compare the ordinary glyph scanner with frozen row references.

This benchmark deliberately uses the exact same page preparation and per-row
analysis calls, in the same order, as ``ocr_find_unreviewed_glyph_rows``.  It
adds no OCR policy, anchor, boundary-repair, headword-memory, or benchmark-only
parser wrappers.  The only extra work is serializing scanner rows into the
frozen-reference shape and comparing them with the reference JSONL.
"""

import argparse
import contextlib
import io
import time
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_compare_forward_reference import _compare_page, _load_reference, _short_text
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_split_facit_benchmark import (
    _verify_equivalent,
    load_split_facit_with_typography,
)


def _observed_row(state: dict) -> dict:
    return {
        "exact": bool(state.get("fully_exact", False)),
        "text": str(state.get("text") or ""),
        "source_pixels": int(state.get("source_pixels") or 0),
        "covered_pixels": int(state.get("covered_pixels") or 0),
    }


def _print_mismatch(page: int, key, why, expected, observed) -> None:
    print(f"DIFF page={page} column={key[0]} row={key[1]}: {why}", flush=True)
    if expected is not None:
        print(
            f"  ref pixels={expected['source_pixels']} text={expected['text']!r}",
            flush=True,
        )
    if observed is not None:
        print(
            f"  new pixels={observed['source_pixels']} covered={observed['covered_pixels']} "
            f"exact={observed['exact']} text={observed['text']!r}",
            flush=True,
        )


def _quiet_call_preserving_warnings(function, *args, **kwargs):
    """Run ordinary scanner code quietly, replaying only real warning lines."""
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            return function(*args, **kwargs)
    finally:
        for line in captured.getvalue().splitlines():
            if "VARNING" in line:
                print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare the ordinary scanner row-by-row with frozen references."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--split-facit", type=Path)
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    # Kept for CLI compatibility with the historical benchmark stack.  The
    # ordinary scanner has no separate boundary-radius knob here.
    ap.add_argument("--boundary-radius", type=int, default=6)
    ap.add_argument("--max-diffs", type=int, default=20)
    args = ap.parse_args()

    benchmark_started = time.perf_counter()
    models = load_facit_with_typography(args.facit)
    if args.split_facit is not None:
        split_models = load_split_facit_with_typography(args.split_facit)
        _verify_equivalent(models, split_models)

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    total_reference = 0
    total_actual = 0
    total_equal = 0
    total_mismatches = 0
    printed_diffs = 0
    timings: list[tuple[float, int, int, int, str]] = []

    for page in pages:
        reference = _load_reference(args.reference_dir / f"page-{page:03d}.jsonl")
        context = _quiet_call_preserving_warnings(
            page_editor.build_page_context_pixel_array,
            args.jsonl,
            page,
            args.threshold,
        )
        context["quiet_successful_ownership"] = True

        actual: dict[tuple[int, int], dict] = {}
        page_mismatches: list[tuple] = []
        current_column: int | None = None
        column_started = time.perf_counter()
        column_rows = 0

        def finish_column(column: int | None) -> None:
            nonlocal printed_diffs, column_started, column_rows
            if column is None:
                return
            expected_column = {
                key: value for key, value in reference.items() if int(key[0]) == int(column)
            }
            actual_column = {
                key: value for key, value in actual.items() if int(key[0]) == int(column)
            }
            mismatches = _compare_page(expected_column, actual_column)
            page_mismatches.extend(mismatches)
            all_keys = set(expected_column) | set(actual_column)
            equal = len(all_keys) - len(mismatches)
            elapsed = time.perf_counter() - column_started
            print(
                f"page={page} column={column} rows={column_rows} "
                f"equal={equal}/{len(all_keys)} mismatches={len(mismatches)} "
                f"time={elapsed:.3f}s",
                flush=True,
            )
            for key, why, expected, observed in mismatches:
                if printed_diffs >= args.max_diffs:
                    break
                printed_diffs += 1
                _print_mismatch(page, key, why, expected, observed)

        for position in context["positions"]:
            column = int(position[0])
            if current_column is None:
                current_column = column
                column_started = time.perf_counter()
                column_rows = 0
            elif column != current_column:
                finish_column(current_column)
                current_column = column
                column_started = time.perf_counter()
                column_rows = 0

            started = time.perf_counter()
            state = _quiet_call_preserving_warnings(
                page_editor.load_review_state_pixel_array,
                context,
                position,
                models,
            )
            elapsed = time.perf_counter() - started
            key = (column, int(position[1]))
            actual[key] = _observed_row(state)
            column_rows += 1
            timings.append(
                (
                    elapsed,
                    page,
                    key[0],
                    key[1],
                    str(state.get("text") or ""),
                )
            )

        finish_column(current_column)

        all_keys = set(reference) | set(actual)
        equal = len(all_keys) - len(page_mismatches)
        total_reference += len(reference)
        total_actual += len(actual)
        total_equal += equal
        total_mismatches += len(page_mismatches)

    total_wall = time.perf_counter() - benchmark_started
    row_time = sum(item[0] for item in timings)
    average_row = row_time / len(timings) if timings else 0.0
    print(
        "summary: "
        f"pages={len(pages)} rows={total_actual} equal={total_equal} "
        f"mismatches={total_mismatches} total_time={total_wall:.3f}s "
        f"average_row_time={average_row:.6f}s",
        flush=True,
    )
    print("slowest-rows: top=5", flush=True)
    for rank, (elapsed, page, column, row, text) in enumerate(
        sorted(timings, reverse=True)[:5], start=1
    ):
        print(
            f"slowest-row: rank={rank} page={page} column={column} row={row} "
            f"time={elapsed:.3f}s text={_short_text(text)!r}",
            flush=True,
        )

    return 1 if total_mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
