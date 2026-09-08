from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_left_edge_local_index import prepare_local_fingerprint_indexes
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry
from .ocr_row_start_band_search import ranked_exact_row_start_band_hits
from .ocr_row_start_prefix_fallback import exact_mature_prefix_row_starts
from .ocr_whole_column_row_walk import walk_row_starts


def _column_bounds(context: dict, column_index: int) -> tuple[int, int, int, int]:
    columns = context["row_map"].get("columns") or []
    if not 0 <= column_index < len(columns):
        raise ValueError(f"column {column_index} does not exist")
    column = columns[column_index]
    rows = column.get("rows") or []
    if not rows:
        raise ValueError(f"column {column_index} has no reference rows")
    owners = context["pixel_owners"]
    left = int(column.get("crop_left", column.get("left", 0)))
    content_left = (context.get("column_content_lefts") or {}).get(column_index)
    if content_left is not None:
        left = max(left, int(content_left))
    right = int(column.get("crop_right", column.get("right", owners.width)))
    top = min(int(row["page_top"]) for row in rows)
    bottom = max(int(row["page_bottom"]) for row in rows)
    return max(0, left), min(owners.width, right), max(0, top), min(owners.height, bottom)


def _black_pixels(context: dict, bounds: tuple[int, int, int, int]) -> set[tuple[int, int]]:
    left, right, top, bottom = bounds
    gray = context["pixel_gray_page"]
    threshold = int(context["threshold"])
    pixels = gray.load()
    return {(x, y) for y in range(top, bottom) for x in range(left, right) if int(pixels[x, y]) < threshold}


def _old_row_for_y(rows: list[dict], y: int) -> int | None:
    for index, row in enumerate(rows):
        if int(row["page_top"]) <= y < int(row["page_bottom"]):
            return index
    return None


def _start_search_ranges(geometry, tolerance: int) -> tuple[tuple[int, int], ...]:
    if tolerance < 0:
        raise ValueError("start tolerance must be non-negative")
    centers = (
        int(geometry.homonym_start_x),
        int(geometry.headword_start_x),
        int(geometry.continuation_start_x),
    )
    return tuple((center - tolerance, center + tolerance) for center in centers)


def main() -> int:
    ap = argparse.ArgumentParser(description="Shadow experiment: find rows one at a time from whole-column pixels; old segmentation is comparison only.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=39)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-x", type=int, default=46)
    ap.add_argument("--headword-x", type=int, default=57)
    ap.add_argument("--continuation-x", type=int, default=68)
    ap.add_argument("--start-x-tolerance", type=int, default=7)
    ap.add_argument("--start-observation-right-slack", type=int, default=12)
    ap.add_argument("--max-row-distance", type=int, default=24)
    ap.add_argument("--min-steps", type=int, default=3)
    ap.add_argument("--min-baseline-delta", type=int, default=8)
    args = ap.parse_args()

    models = tuple(load_canonical_facit_with_typography(args.facit))
    prepared_started = perf_counter()
    prepared = prepare_local_fingerprint_indexes(models, max_steps=8, min_steps=args.min_steps, max_row_gap=1)
    print(f"shadow-fingerprints: models={len(models)} build={perf_counter()-prepared_started:.4f}s reusable=yes", flush=True)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    start_ranges = _start_search_ranges(geometry, args.start_x_tolerance)
    print(
        f"shadow-column: page={args.page} column={args.column} bounds={bounds} black={len(black)} "
        f"models={len(models)} geometry={geometry.homonym_start_x}/{geometry.headword_start_x}/"
        f"{geometry.continuation_start_x} start_ranges={start_ranges} "
        f"observation_right_slack={args.start_observation_right_slack}",
        flush=True,
    )
    hits_started = perf_counter()
    hits = ranked_exact_row_start_band_hits(
        black,
        prepared=prepared,
        start_ranges=start_ranges,
        min_steps=args.min_steps,
        max_steps=8,
        max_row_gap=1,
        observation_right_slack=args.start_observation_right_slack,
    )
    print(f"shadow-column: exact-local-hits={len(hits)} search={perf_counter()-hits_started:.4f}s", flush=True)

    fallback_started = perf_counter()
    fallback_starts = exact_mature_prefix_row_starts(
        black,
        models,
        start_ranges=start_ranges,
        max_row_gap=1,
    )
    print(
        f"shadow-column: mature-prefix-starts={len(fallback_starts)} "
        f"search={perf_counter()-fallback_started:.4f}s",
        flush=True,
    )

    _left, _right, top, bottom = bounds
    shadow = walk_row_starts(
        hits,
        models=models,
        geometry=geometry,
        start_y=top,
        end_y=bottom - 1,
        max_row_distance=args.max_row_distance,
        min_steps=args.min_steps,
        min_baseline_delta=args.min_baseline_delta,
        fallback_starts=fallback_starts,
    )
    old_rows = (context["row_map"].get("columns") or [])[args.column].get("rows") or []
    matched_old: set[int] = set()
    for row in shadow:
        old_index = _old_row_for_y(old_rows, row.start.top_y)
        if old_index is not None:
            matched_old.add(old_index)
        old_text = "none" if old_index is None else str(old_index)
        print(
            f"shadow-row: new={row.index} old={old_text} search={row.search_from_y} "
            f"top={row.start.top_y} baseline={row.start.baseline} next={row.next_search_y} "
            f"start={row.start.label!r}/{row.start.style}@x{row.start.x} steps={row.start.steps} "
            f"source={row.source}",
            flush=True,
        )
    unmatched = [i for i in range(len(old_rows)) if i not in matched_old]
    print(f"shadow-summary: new_rows={len(shadow)} old_rows={len(old_rows)} matched_old={len(matched_old)} unmatched_old={len(unmatched)}", flush=True)
    for index in unmatched:
        row = old_rows[index]
        print(f"shadow-old-only: old={index} y={int(row['page_top'])}..{int(row['page_bottom'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
