from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry
from .ocr_shadow_whole_column import _black_pixels, _column_bounds, _start_search_ranges
from .ocr_whole_column_profile import (
    build_profile_fragment_index,
    profile_guided_exact_hits,
    walk_profile_row_starts,
    whole_column_left_profile,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Shadow experiment: build one dense whole-column left-ink profile, "
            "find partial facit-profile substrings at legal row-start x positions, "
            "then verify complete glyph pixels behind the profile."
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
    ap.add_argument("--profile-max-x", type=int, default=75)
    ap.add_argument("--min-profile-rows", type=int, default=2)
    ap.add_argument("--max-profile-rows", type=int, default=8)
    ap.add_argument("--min-profile-ink-rows", type=int, default=2)
    ap.add_argument("--max-row-distance", type=int, default=20)
    ap.add_argument("--min-baseline-delta", type=int, default=8)
    ap.add_argument("--dump-profile", action="store_true")
    args = ap.parse_args()

    models_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    fragment_index = build_profile_fragment_index(
        models,
        min_rows=args.min_profile_rows,
        max_rows=args.max_profile_rows,
        min_ink_rows=args.min_profile_ink_rows,
    )
    print(
        f"profile-shadow-models: models={len(models)} buckets={len(fragment_index)} "
        f"build={perf_counter()-models_started:.4f}s",
        flush=True,
    )

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    start_ranges = _start_search_ranges(geometry, args.start_x_tolerance)
    _left, _right, top, bottom = bounds

    profile_started = perf_counter()
    profile = whole_column_left_profile(
        black,
        min_y=top,
        max_y=bottom - 1,
        min_x=0,
        max_x=args.profile_max_x,
    )
    profile_seconds = perf_counter() - profile_started
    ink_profile_rows = sum(x is not None for x in profile)
    print(
        f"profile-shadow-column: page={args.page} column={args.column} bounds={bounds} "
        f"black={len(black)} profile_rows={len(profile)} ink_rows={ink_profile_rows} "
        f"profile_max_x={args.profile_max_x} start_ranges={start_ranges} "
        f"profile={profile_seconds:.4f}s",
        flush=True,
    )

    if args.dump_profile:
        for offset, x in enumerate(profile):
            y = top + offset
            print(f"profile-y: y={y} left_x={'none' if x is None else x}")

    match_started = perf_counter()
    hits = profile_guided_exact_hits(
        black,
        profile,
        profile_min_y=top,
        fragment_index=fragment_index,
        allowed_translate_x_ranges=start_ranges,
        min_rows=args.min_profile_rows,
        max_rows=args.max_profile_rows,
    )
    match_seconds = perf_counter() - match_started
    print(
        f"profile-shadow-hits: exact={len(hits)} search={match_seconds:.4f}s",
        flush=True,
    )

    rows = walk_profile_row_starts(
        hits,
        start_y=top,
        end_y=bottom - 1,
        max_row_distance=args.max_row_distance,
        min_baseline_delta=args.min_baseline_delta,
    )
    for row in rows:
        hit = row.hit
        print(
            f"profile-shadow-row: new={row.index} search={row.search_from_y}..{row.search_to_y} "
            f"profile={hit.profile_start_y}..{hit.profile_end_y} "
            f"top={hit.top_y} baseline={hit.baseline} bottom={hit.bottom_y} "
            f"start={hit.model.label!r}/{hit.model.style}@x{hit.x} "
            f"profile_rows={hit.profile_rows} ink_rows={hit.profile_ink_rows} "
            f"glyph_pixels={len(hit.model.pixels)} next={row.next_search_y}",
            flush=True,
        )
    print(f"profile-shadow-summary: rows={len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
