from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_column_left_profile import build_column_left_profile
from .ocr_directional_page_benchmark import _isolated_profile_segments
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Experimental whole-column baseline seeding from the leftmost "
            "profile pixels. Only globally-leftmost glyph pixels may anchor."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=36)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    total_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds

    profile = build_column_left_profile(
        residual.rows,
        top=column_top,
        bottom=column_bottom,
        left=column_left,
        right=column_right,
    )
    segments = _isolated_profile_segments(profile)

    columns = context["row_map"].get("columns") or []
    reference_rows = columns[args.column].get("rows") or []
    if args.rows > 0:
        reference_rows = reference_rows[: args.rows]

    # Compile only globally-leftmost glyph pixels. Multiple y values are useful:
    # an accent, descender or capital shape can make the left edge occur away
    # from the ordinary body row.
    left_anchors: list[tuple[object, int]] = []
    for item in library.models:
        for model_x, model_y in item.model.pixels:
            if model_x == item.min_x:
                left_anchors.append((item, model_y))

    proposals = 0
    exact_checks = 0
    exact_hits = 0
    baseline_hist: Counter[int] = Counter()
    baseline_labels: dict[int, set[str]] = defaultdict(set)
    segment_results: list[tuple[int, int, int, int, tuple[int, ...]]] = []

    match_started = perf_counter()
    for segment_top, segment_bottom, min_x in segments:
        # Only page rows that actually attain the segment's leftmost x are
        # possible anchors for a globally-leftmost glyph pixel.
        anchor_ys = tuple(
            y
            for y in range(segment_top, segment_bottom + 1)
            if profile.at(y) == min_x
        )
        segment_baselines: Counter[int] = Counter()

        seen: set[tuple[int, int, int]] = set()
        for page_y in anchor_ys:
            for item, model_y in left_anchors:
                tx = min_x - item.min_x
                baseline = page_y - model_y
                key = (id(item.model), tx, baseline)
                if key in seen:
                    continue
                seen.add(key)
                proposals += 1

                top = baseline + item.model.min_y
                bottom = baseline + item.model.max_y
                if top < column_top or bottom >= column_bottom:
                    continue
                if tx + item.max_x >= column_right:
                    continue

                exact_checks += 1
                if not all(
                    (tx + x, baseline + y) in black
                    for x, y in item.model.pixels
                ):
                    continue

                exact_hits += 1
                baseline_hist[baseline] += 1
                segment_baselines[baseline] += 1
                baseline_labels[baseline].add(item.model.label)

        # The strongest baselines are useful even when several glyph models are
        # raster homonyms. Keep ties: the whole point is to see whether those
        # homonyms collapse onto the same geometric baseline.
        if segment_baselines:
            peak = max(segment_baselines.values())
            strongest = tuple(sorted(
                baseline for baseline, count in segment_baselines.items()
                if count == peak
            ))
        else:
            strongest = ()
        segment_results.append(
            (segment_top, segment_bottom, min_x, len(anchor_ys), strongest)
        )

    matching_seconds = perf_counter() - match_started

    print(
        f"leftmost-seed-start: page={args.page} column={args.column} "
        f"models={len(models)} left_anchors={len(left_anchors)} "
        f"segments={len(segments)} reference_rows={len(reference_rows)}",
        flush=True,
    )
    for top, bottom, min_x, anchor_count, strongest in segment_results:
        detail = ",".join(
            f"{baseline}:{'/'.join(sorted(baseline_labels[baseline]))}"
            for baseline in strongest
        )
        print(
            f"leftmost-seed-segment: y={top}..{bottom} min_x={min_x} "
            f"anchor_rows={anchor_count} strongest=[{detail}]",
            flush=True,
        )

    print(
        "leftmost-seed-baselines: "
        + " ".join(
            f"{baseline}:{baseline_hist[baseline]}"
            for baseline in sorted(baseline_hist)
        ),
        flush=True,
    )
    print(
        f"leftmost-seed-done: proposals={proposals} exact_checks={exact_checks} "
        f"exact_hits={exact_hits} distinct_baselines={len(baseline_hist)} "
        f"matching={matching_seconds:.6f}s total={perf_counter()-total_started:.6f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
