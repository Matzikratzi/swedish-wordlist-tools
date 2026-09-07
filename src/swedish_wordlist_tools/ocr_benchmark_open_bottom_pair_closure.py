from __future__ import annotations

"""Benchmark strict open-bottom pair closure only after ordinary fast-path failure."""

import argparse
from pathlib import Path
from statistics import median
from time import perf_counter

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_probe_open_bottom_pair_closure import probe_pair_closure
from .ocr_review_page_pixel_array_shared import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _xrange(value) -> str:
    if value is None:
        return "none"
    return f"{value[0]}..{value[1]}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Run ordinary analysis, then strict two-row open-bottom closure only "
            "where the ordinary exact fast path did not solve the upper row."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--baseline-radius", type=int, default=1)
    ap.add_argument("--beam-width", type=int, default=128)
    args = ap.parse_args()
    if args.baseline_radius < 0:
        raise ValueError("--baseline-radius must be >= 0")
    if args.beam_width < 1:
        raise ValueError("--beam-width must be >= 1")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    probes = 0
    closed = 0
    ordinary_times: list[float] = []
    closure_times: list[float] = []

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        positions = list(context["positions"])
        state_cache: dict[tuple[int, int], tuple[dict, float]] = {}

        def load(position: tuple[int, int]) -> tuple[dict, float]:
            cached = state_cache.get(position)
            if cached is not None:
                return cached
            started = perf_counter()
            state = load_review_state_pixel_array(context, position, models)
            elapsed = perf_counter() - started
            state_cache[position] = (state, elapsed)
            return state, elapsed

        print(f"pair-closure: page {page}: {len(positions)} rows", flush=True)
        for position in positions:
            column, row = map(int, position)
            lower_position = (column, row + 1)
            if lower_position not in positions:
                continue
            upper_state, upper_elapsed = load(position)
            # The state records whether its accepted result came from the exact
            # fast path.  Only failures are candidates for the second if-satz.
            if bool(upper_state.get("exact_fast_path")):
                continue
            lower_state, lower_elapsed = load(lower_position)
            probes += 1
            ordinary_pair_elapsed = upper_elapsed + lower_elapsed
            started = perf_counter()
            result = probe_pair_closure(
                context,
                position,
                upper_state,
                lower_state,
                models,
                threshold=args.threshold,
                baseline_radius=args.baseline_radius,
                beam_width=args.beam_width,
            )
            closure_elapsed = perf_counter() - started
            ordinary_times.append(ordinary_pair_elapsed)
            closure_times.append(closure_elapsed)
            closed += int(result["closed"])
            print(
                f"pair-closure-row: page {page} column {column} row {row}/{row+1} "
                f"ordinary={ordinary_pair_elapsed:.3f}s closure={closure_elapsed:.3f}s "
                f"closed={int(result['closed'])} target={result['target_pixels']} "
                f"selected={result['selected_pixels']} missing={result['missing_pixels']} "
                f"extra={result['extra_pixels']} missing_x={_xrange(result['missing_x'])} "
                f"extra_x={_xrange(result['extra_x'])}",
                flush=True,
            )

    print(f"pair-closure: closed {closed}/{probes} fast-path-failure pairs", flush=True)
    if ordinary_times:
        ratios = [c / o for o, c in zip(ordinary_times, closure_times) if o > 0]
        print(
            f"pair-closure: ordinary median={median(ordinary_times):.3f}s "
            f"closure median={median(closure_times):.3f}s "
            f"ratio median={median(ratios):.2f}x",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
