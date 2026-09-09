from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk, find_next_baseline_up
from .ocr_canonical_facit import load_canonical_facit_with_typography
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Benchmark directional OCR: first glyph top-down, later glyphs "
            "baseline-up on incrementally maintained residual pixels. The old "
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
    args = ap.parse_args()

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

    columns = context["row_map"].get("columns") or []
    if not 0 <= args.column < len(columns):
        raise ValueError(f"column out of range: {args.column}")
    reference_rows = columns[args.column].get("rows") or []
    if args.rows > 0:
        reference_rows = reference_rows[: args.rows]

    inferred = infer_page_start_geometry(
        page_residual.rows,
        reference_rows,
        tolerance=args.start_x_tolerance,
    )
    if not inferred.ranges:
        raise ValueError("could not infer row-start x ranges from this page")
    ranges = inferred.ranges
    _column_left, column_right, _column_top, _column_bottom = bounds

    print(
        f"directional-page-start: page={args.page} column={args.column} rows={len(reference_rows)} "
        f"models={len(models)} model_compile={models_seconds:.4f}s page_prepare={page_seconds:.4f}s "
        f"black={len(black)} bounds={bounds} start_centers={inferred.centers} ranges={ranges} "
        f"start_observations={len(inferred.observations)}",
        flush=True,
    )

    solved = 0
    unresolved = 0
    glyphs_total = 0
    matching_started = perf_counter()

    for row_index, row in enumerate(reference_rows):
        row_started = perf_counter()
        row_top = int(row["page_top"])
        row_bottom = int(row["page_bottom"])
        row_black = _row_black(page_residual.rows, top=row_top, bottom=row_bottom)
        residual = ResidualInk(row_black)

        first, first_search = first_glyph_top_down(
            residual.pixels,
            residual.rows,
            library,
            row_top=row_top,
            row_bottom=row_bottom,
            allowed_translate_x_ranges=ranges,
        )
        if first is None:
            unresolved += 1
            print(
                f"directional-row: row={row_index} y={row_top}..{row_bottom-1} "
                f"status=unresolved-first first_y={first_search.y} "
                f"candidates={len(first_search.candidates)} pixels={len(row_black)} "
                f"time={perf_counter()-row_started:.4f}s",
                flush=True,
            )
            continue

        labels = [first.model.label]
        residual.consume(first.pixels)
        current_left = first.left
        baseline = first.baseline
        glyphs = 1
        status = "complete"
        stop_candidates = 0

        while glyphs < args.max_glyphs:
            hit, candidates = find_next_baseline_up(
                residual.pixels,
                residual.rows,
                library,
                baseline=baseline,
                row_top=row_top,
                after_left=current_left,
                column_right=column_right,
            )
            if hit is None:
                rest = _relevant_residual(
                    residual,
                    after_left=current_left,
                    row_top=row_top,
                    row_bottom=row_bottom,
                )
                if rest:
                    status = "unresolved"
                    stop_candidates = len(candidates)
                break

            labels.append(hit.model.label)
            residual.consume(hit.pixels)
            current_left = hit.left
            glyphs += 1
        else:
            status = "max-glyphs"

        glyphs_total += glyphs
        if status == "complete":
            solved += 1
        else:
            unresolved += 1

        remaining = _relevant_residual(
            residual,
            after_left=current_left,
            row_top=row_top,
            row_bottom=row_bottom,
        )
        print(
            f"directional-row: row={row_index} y={row_top}..{row_bottom-1} "
            f"status={status} first_y={first_search.y} baseline={baseline} "
            f"glyphs={glyphs} text={''.join(labels)!r} remaining={len(remaining)} "
            f"stop_candidates={stop_candidates} time={perf_counter()-row_started:.4f}s",
            flush=True,
        )

    matching_seconds = perf_counter() - matching_started
    print(
        f"directional-page-done: rows={len(reference_rows)} solved={solved} unresolved={unresolved} "
        f"glyphs={glyphs_total} matching={matching_seconds:.4f}s total={perf_counter()-total_started:.4f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
