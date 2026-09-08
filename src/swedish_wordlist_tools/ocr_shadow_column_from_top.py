from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from time import perf_counter

from .ocr_candidate_survival import glyph_left_profile, run_candidate_survival
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry
from .ocr_shadow_whole_column import _black_pixels, _column_bounds, _start_search_ranges


def _row_page_span(context: dict, column: int, row_index: int) -> tuple[int, int]:
    columns = context["row_map"].get("columns") or []
    if not 0 <= column < len(columns):
        raise ValueError(f"column out of range: {column}")
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        raise ValueError(f"row out of range: column={column} row={row_index}")
    row = rows[row_index]
    top = int(row["page_top"])
    bottom = int(row["page_bottom"])
    if bottom <= top:
        raise ValueError(f"invalid row span: {top}..{bottom}")
    return top, bottom


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Shadow experiment: begin at the absolute first text row in a column, "
            "run whole-column candidate survival across that row, and report the "
            "baseline hypotheses produced by the glyph matches. Existing row "
            "geometry is used only to delimit the shadow experiment."
        )
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
    ap.add_argument("--show-steps", action="store_true")
    ap.add_argument("--show-completed", type=int, default=80)
    args = ap.parse_args()

    models_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    print(
        f"column-top-models: models={len(models)} load={perf_counter()-models_started:.4f}s",
        flush=True,
    )

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    row_top, row_bottom = _row_page_span(context, args.column, 0)

    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    ranges = _start_search_ranges(geometry, args.start_x_tolerance)

    print(
        f"column-top-row: page={args.page} column={args.column} row=0 "
        f"top={row_top} bottom={row_bottom} y={row_top}..{row_bottom-1} "
        f"bounds={bounds} ranges={ranges}",
        flush=True,
    )

    started = perf_counter()
    result = run_candidate_survival(
        black,
        models,
        start_y=row_top,
        end_y=row_bottom - 1,
        allowed_translate_x_ranges=ranges,
    )
    seconds = perf_counter() - started

    total_died = sum(step.died for step in result.steps)
    total_completed = sum(step.completed for step in result.steps)
    peak_live = max((step.after for step in result.steps), default=0)
    print(
        f"column-top-summary: seeded={result.seeded} completed={len(result.completed)} "
        f"completed_events={total_completed} died={total_died} peak_live={peak_live} "
        f"steps={len(result.steps)} search={seconds:.4f}s",
        flush=True,
    )

    baseline_counts = Counter(hit.baseline for hit in result.completed)
    for baseline, count in sorted(
        baseline_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        print(f"column-top-baseline: y={baseline} hits={count}", flush=True)

    if args.show_steps:
        for step in result.steps:
            profile = -1 if step.profile_x is None else step.profile_x
            print(
                f"column-top-step: y={step.y} profile={profile} born={step.born} "
                f"before={step.before} after={step.after} died={step.died} "
                f"completed={step.completed}",
                flush=True,
            )

    for i, hit in enumerate(result.completed[: max(0, args.show_completed)]):
        profile = ",".join(
            "_" if value is None else str(value)
            for value in glyph_left_profile(hit.model)
        )
        print(
            f"column-top-hit: n={i} seed={hit.seed_y} top={hit.top_y} "
            f"baseline={hit.baseline} bottom={hit.bottom_y} "
            f"start={hit.model.label!r}/{hit.model.style}@x{hit.x} "
            f"front={hit.front_rows} hidden={hit.hidden_rows} "
            f"profile=[{profile}] glyph_pixels={len(hit.model.pixels)}",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
