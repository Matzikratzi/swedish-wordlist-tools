from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_left_edge_prefix_hypotheses import build_prefix_index, scan_prefix_candidate_lifetimes
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _left_rows(
    black: set[tuple[int, int]], *, min_x: int, y0: int, y1: int
) -> tuple[tuple[int, int], ...]:
    by_y: dict[int, int] = {}
    for x, y in black:
        if y < y0 or y > y1 or x < min_x:
            continue
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(sorted(by_y.items()))


def _fmt_relations(relations: tuple[tuple[int, int], ...]) -> str:
    return " ".join(f"({dy:+d},{dx:+d})" for dy, dx in relations)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Show facit-prefix lifetimes and exact raster tests along a source left contour."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--y0", type=int, required=True)
    ap.add_argument("--y1", type=int, required=True)
    ap.add_argument("--x0", type=int, default=39)
    ap.add_argument("--x1", type=int, default=75)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    if args.y1 < args.y0:
        raise ValueError("--y1 must be >= --y0")
    if args.x1 < args.x0:
        raise ValueError("--x1 must be >= --x0")

    models = tuple(load_canonical_facit_with_typography(args.facit))
    index = build_prefix_index(models, max_row_gap=1)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    black = _black_pixels(context, _column_bounds(context, args.column))

    print(
        f"prefix-index: models={len(models)} prefixes={len(index.buckets)} "
        f"max_relations={index.max_relations}",
        flush=True,
    )

    previous_rows: tuple[tuple[int, int], ...] | None = None
    for min_x in range(args.x0, args.x1 + 1):
        rows = _left_rows(black, min_x=min_x, y0=args.y0, y1=args.y1)
        # Different x thresholds that expose the same contour are identical work.
        if rows == previous_rows:
            continue
        previous_rows = rows
        runs = scan_prefix_candidate_lifetimes(rows, black=black, index=index, max_row_gap=1)
        if not runs:
            continue

        print(f"scan-x={min_x} rows={rows}", flush=True)
        for number, run in enumerate(runs):
            print(
                f"  run={number} source_rows={run.source_start_row}..{run.source_end_row} "
                f"steps={len(run.relations)} surviving={run.surviving_candidates} "
                f"rels={_fmt_relations(run.relations)}",
                flush=True,
            )
            for test in run.mature_tests:
                print(
                    f"    mature-at={test.source_end_row} glyph={test.model.label!r}/{test.model.style} "
                    f"model-start={test.model_start_row} x={test.translate_x} baseline={test.baseline} "
                    f"pixels={len(test.model.pixels)} exact={'YES' if test.exact else 'no'}",
                    flush=True,
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
