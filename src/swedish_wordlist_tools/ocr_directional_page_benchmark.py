from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import BaselineMatch, BaselineUpStats, CompiledGlyphLibrary, ResidualInk, find_next_baseline_up
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_column_left_profile import build_column_left_profile
from .ocr_page_start_geometry import infer_page_start_geometry
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_directional import first_glyph_top_down
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _row_black(page_rows: dict[int, set[int]], *, top: int, bottom: int) -> set[tuple[int, int]]:
    return {
        (x, y)
        for y in range(top, bottom)
        for x in page_rows.get(y, ())
    }


def _relevant_residual(
    residual: ResidualInk,
    *,
    after_left: int,
    row_top: int,
    row_bottom: int,
) -> set[tuple[int, int]]:
    return {
        (x, y)
        for x, y in residual.pixels
        if x > after_left and row_top <= y < row_bottom
    }


def _match_summary(hit: BaselineMatch) -> str:
    return (
        f"{hit.model.label!r}/{hit.model.style}@x{hit.left}..{hit.right} "
        f"tx={hit.tx} baseline={hit.baseline} discovered_y={hit.discovered_y} "
        f"pixels={len(hit.pixels)} sources={hit.model.sources}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Benchmark directional OCR: build one whole-column left profile, "
            "find first glyphs top-down from that profile, and find later glyphs "
            "from the dynamically maintained residual left profile. The old "
            "row map is used only to provide benchmark row boundaries."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=30)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0, help="0 means all reference rows in the column")
    ap.add_argument("--max-glyphs", type=int, default=100)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--start-x-tolerance", type=int, default=4)
    ap.add_argument(
        "--trace-row",
        type=int,
        action="append",
        default=[],
        help="print candidate decisions for this zero-based row index; repeat for multiple rows",
    )
    args = ap.parse_args()
    trace_rows = set(args.trace_row)

    total_started = perf_counter()

    models_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)
    models_seconds = perf_counter() - models_started

    page_started = perf_counter()
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    page_residual = ResidualInk(black)
    page_seconds = perf_counter() - page_started

    column_left, column_right, column_top, column_bottom = bounds
    profile_started = perf_counter()
    left_profile = build_column_left_profile(
        page_residual.rows,
        top=column_top,
        bottom=column_bottom,
        left=column_left,
        right=column_right,
    )
    profile_seconds = perf_counter() - profile_started
    profile_events = left_profile.changes()

    columns = context["row_map"].get("columns") or []
    if not 0 <= args.column < len(columns):
        raise ValueError(f"column out of range: {args.column}")
    reference_rows = columns[args.column].get("rows") or []
    if args.rows > 0:
        reference_rows = reference_rows[: args.rows]

    geometry_started = perf_counter()
    inferred = infer_page_start_geometry(
        left_profile,
        reference_rows,
        tolerance=args.start_x_tolerance,
    )
    geometry_seconds = perf_counter() - geometry_started
    if not inferred.ranges:
        raise ValueError("could not infer row-start x ranges from this page")
    ranges = inferred.ranges

    print(
        f"directional-page-start: page={args.page} column={args.column} rows={len(reference_rows)} "
        f"models={len(models)} model_compile={models_seconds:.4f}s page_prepare={page_seconds:.4f}s "
        f"profile_build={profile_seconds:.6f}s geometry={geometry_seconds:.6f}s "
        f"profile_rows={len(left_profile.values)} profile_events={len(profile_events)} "
        f"black={len(black)} bounds={bounds} start_centers={inferred.centers} ranges={ranges} "
        f"start_observations={len(inferred.observations)}",
        flush=True,
    )

    solved = 0
    unresolved = 0
    glyphs_total = 0
    matching_started = perf_counter()

    setup_total = 0.0
    first_total = 0.0
    baseline_total = 0.0
    consume_total = 0.0
    residual_total = 0.0
    baseline_calls = 0
    baseline_hits = 0
    baseline_misses = 0
    baseline_stats = BaselineUpStats()

    for row_index, row in enumerate(reference_rows):
        row_started = perf_counter()
        row_top = int(row["page_top"])
        row_bottom = int(row["page_bottom"])
        trace = row_index in trace_rows

        phase_started = perf_counter()
        row_black = _row_black(page_residual.rows, top=row_top, bottom=row_bottom)
        residual = ResidualInk(row_black)
        row_setup = perf_counter() - phase_started
        setup_total += row_setup

        phase_started = perf_counter()
        first, first_search = first_glyph_top_down(
            residual.pixels,
            residual.rows,
            library,
            row_top=row_top,
            row_bottom=row_bottom,
            allowed_translate_x_ranges=ranges,
            left_profile=left_profile,
        )
        row_first = perf_counter() - phase_started
        first_total += row_first

        if first is None:
            unresolved += 1
            row_seconds = perf_counter() - row_started
            row_other = max(0.0, row_seconds - row_setup - row_first)
            print(
                f"directional-row: row={row_index} y={row_top}..{row_bottom-1} "
                f"status=unresolved-first first_y={first_search.y} "
                f"candidates={len(first_search.candidates)} pixels={len(row_black)} "
                f"time={row_seconds:.4f}s setup={row_setup:.6f}s first={row_first:.6f}s "
                f"baseline=0.000000s consume=0.000000s residual=0.000000s other={row_other:.6f}s",
                flush=True,
            )
            continue

        labels = [first.model.label]
        phase_started = perf_counter()
        residual.consume(first.pixels)
        row_consume = perf_counter() - phase_started
        consume_total += row_consume
        row_baseline = 0.0
        row_residual = 0.0
        row_baseline_calls = 0
        current_left = first.left
        baseline = first.baseline
        explained_bottom = max(y for _x, y in first.pixels)
        glyphs = 1
        status = "complete"
        stop_candidates = 0

        if trace:
            print(
                f"directional-trace: row={row_index} step=0 accepted="
                f"{first.model.label!r}/{first.model.style}@x{first.left}..{first.right} "
                f"baseline={first.baseline} pixels={len(first.pixels)} first_y={first_search.y}",
                flush=True,
            )

        while glyphs < args.max_glyphs:
            phase_started = perf_counter()
            hit, candidates = find_next_baseline_up(
                residual.pixels,
                residual.rows,
                library,
                baseline=baseline,
                row_top=row_top,
                profile_bottom=explained_bottom,
                after_left=current_left,
                column_right=column_right,
                stats=baseline_stats,
            )
            elapsed = perf_counter() - phase_started
            row_baseline += elapsed
            baseline_total += elapsed
            row_baseline_calls += 1
            baseline_calls += 1

            if trace:
                print(
                    f"directional-trace: row={row_index} step={glyphs} after_left={current_left} "
                    f"profile_bottom={explained_bottom} candidates={len(candidates)} "
                    f"accepted={_match_summary(hit) if hit is not None else None}",
                    flush=True,
                )
                for candidate_index, candidate in enumerate(candidates):
                    print(
                        f"directional-trace-candidate: row={row_index} step={glyphs} "
                        f"n={candidate_index} {_match_summary(candidate)}",
                        flush=True,
                    )

            if hit is None:
                baseline_misses += 1
                phase_started = perf_counter()
                rest = _relevant_residual(
                    residual,
                    after_left=current_left,
                    row_top=row_top,
                    row_bottom=row_bottom,
                )
                elapsed = perf_counter() - phase_started
                row_residual += elapsed
                residual_total += elapsed
                if rest:
                    status = "unresolved"
                    stop_candidates = len(candidates)
                break

            baseline_hits += 1
            labels.append(hit.model.label)
            phase_started = perf_counter()
            residual.consume(hit.pixels)
            elapsed = perf_counter() - phase_started
            row_consume += elapsed
            consume_total += elapsed
            current_left = hit.left
            explained_bottom = max(explained_bottom, max(y for _x, y in hit.pixels))
            glyphs += 1
        else:
            status = "max-glyphs"

        glyphs_total += glyphs
        if status == "complete":
            solved += 1
        else:
            unresolved += 1

        phase_started = perf_counter()
        remaining = _relevant_residual(
            residual,
            after_left=current_left,
            row_top=row_top,
            row_bottom=row_bottom,
        )
        elapsed = perf_counter() - phase_started
        row_residual += elapsed
        residual_total += elapsed

        if trace and remaining:
            by_y: dict[int, list[int]] = {}
            for x, y in sorted(remaining, key=lambda pixel: (pixel[1], pixel[0])):
                by_y.setdefault(y, []).append(x)
            for y, xs in by_y.items():
                print(
                    f"directional-trace-residual: row={row_index} y={y} "
                    f"left={min(xs)} right={max(xs)} xs={xs}",
                    flush=True,
                )

        row_seconds = perf_counter() - row_started
        row_accounted = row_setup + row_first + row_baseline + row_consume + row_residual
        row_other = max(0.0, row_seconds - row_accounted)
        print(
            f"directional-row: row={row_index} y={row_top}..{row_bottom-1} "
            f"status={status} first_y={first_search.y} baseline={baseline} profile_bottom={explained_bottom} "
            f"glyphs={glyphs} text={''.join(labels)!r} remaining={len(remaining)} "
            f"stop_candidates={stop_candidates} time={row_seconds:.4f}s "
            f"setup={row_setup:.6f}s first={row_first:.6f}s "
            f"baseline={row_baseline:.6f}s/{row_baseline_calls}calls "
            f"consume={row_consume:.6f}s residual={row_residual:.6f}s other={row_other:.6f}s",
            flush=True,
        )

    matching_seconds = perf_counter() - matching_started
    accounted = setup_total + first_total + baseline_total + consume_total + residual_total
    other_total = max(0.0, matching_seconds - accounted)
    average_baseline = baseline_total / baseline_calls if baseline_calls else 0.0
    average_hit = baseline_total / baseline_hits if baseline_hits else 0.0
    print(
        f"directional-timing: setup={setup_total:.6f}s first={first_total:.6f}s "
        f"baseline={baseline_total:.6f}s calls={baseline_calls} hits={baseline_hits} misses={baseline_misses} "
        f"avg_baseline_call={average_baseline:.6f}s baseline_per_hit={average_hit:.6f}s "
        f"consume={consume_total:.6f}s residual={residual_total:.6f}s other={other_total:.6f}s",
        flush=True,
    )
    print(
        f"directional-baseline-stats: calls={baseline_stats.calls} y_rows={baseline_stats.y_rows} "
        f"profile_points={baseline_stats.observed_pixels} model_visits={baseline_stats.model_visits} "
        f"raw_tx={baseline_stats.raw_tx_proposals} in_bounds_tx={baseline_stats.in_bounds_tx} "
        f"duplicate_tx={baseline_stats.duplicate_tx} unique_tx={baseline_stats.unique_tx} "
        f"subset_checks={baseline_stats.subset_checks} exact_hits={baseline_stats.exact_hits}",
        flush=True,
    )
    print(
        f"directional-page-done: rows={len(reference_rows)} solved={solved} unresolved={unresolved} "
        f"glyphs={glyphs_total} matching={matching_seconds:.4f}s total={perf_counter()-total_started:.4f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
