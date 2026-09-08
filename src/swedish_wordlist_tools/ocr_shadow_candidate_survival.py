from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_candidate_survival import run_candidate_survival
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry
from .ocr_shadow_whole_column import _black_pixels, _column_bounds, _start_search_ranges


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Shadow experiment: create glyph hypotheses online and kill them one physical raster row at a time."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=39)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-x", type=int, default=46)
    ap.add_argument("--headword-x", type=int, default=57)
    ap.add_argument("--continuation-x", type=int, default=68)
    ap.add_argument("--start-x-tolerance", type=int, default=7)
    ap.add_argument("--start-y", type=int)
    ap.add_argument("--end-y", type=int)
    ap.add_argument("--show-steps", action="store_true")
    ap.add_argument("--show-completed", type=int, default=80)
    args = ap.parse_args()

    models_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    print(f"survival-models: models={len(models)} load={perf_counter()-models_started:.4f}s", flush=True)

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    ranges = _start_search_ranges(geometry, args.start_x_tolerance)
    _left, _right, top, bottom = bounds
    start_y = top if args.start_y is None else max(top, args.start_y)
    end_y = bottom - 1 if args.end_y is None else min(bottom - 1, args.end_y)

    started = perf_counter()
    result = run_candidate_survival(
        black,
        models,
        start_y=start_y,
        end_y=end_y,
        allowed_translate_x_ranges=ranges,
    )
    seconds = perf_counter() - started
    total_died = sum(step.died for step in result.steps)
    total_completed = sum(step.completed for step in result.steps)
    peak_live = max((step.after for step in result.steps), default=0)
    print(
        f"survival-summary: page={args.page} column={args.column} y={start_y}..{end_y} "
        f"bounds={bounds} black={len(black)} ranges={ranges} seeded={result.seeded} "
        f"completed={len(result.completed)} completed_events={total_completed} "
        f"died={total_died} peak_live={peak_live} steps={len(result.steps)} search={seconds:.4f}s",
        flush=True,
    )

    if args.show_steps:
        for step in result.steps:
            if step.born or step.died or step.completed:
                print(
                    f"survival-step: y={step.y} born={step.born} before={step.before} "
                    f"after={step.after} died={step.died} completed={step.completed}",
                    flush=True,
                )

    for i, hit in enumerate(result.completed[: max(0, args.show_completed)]):
        print(
            f"survival-hit: n={i} seed={hit.seed_y} survived_to={hit.survived_to_y} "
            f"top={hit.top_y} baseline={hit.baseline} bottom={hit.bottom_y} "
            f"start={hit.model.label!r}/{hit.model.style}@x{hit.x} glyph_pixels={len(hit.model.pixels)}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
