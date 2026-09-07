from __future__ import annotations

"""Batch driver for the provisional lower-row-boundary experiment."""

import argparse
from pathlib import Path

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_probe_provisional_row_boundary import probe_provisional_boundary
from .ocr_review_page_pixel_array_shared import build_page_context_pixel_array


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Probe whether moving only unmatched lower ink to row N+1 makes row N exact."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--slow-row-seconds",
        type=float,
        default=0.5,
        help="only print rows whose initial one-row analysis takes at least this long; 0 prints every non-exact row",
    )
    args = ap.parse_args()
    if args.slow_row_seconds < 0:
        raise ValueError("--slow-row-seconds must be >= 0")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    attempted = 0
    exact_after = 0
    moved_total = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        print(f"provisional-boundary: page {page}: {len(context['positions'])} rows", flush=True)

        for position in context["positions"]:
            result = probe_provisional_boundary(context, position, models)
            if result.before_exact:
                continue
            if result.before_seconds < args.slow_row_seconds:
                continue

            attempted += 1
            exact_after += int(result.after_exact)
            moved_total += result.moved_pixels
            print(
                f"provisional-boundary: page {page} column {position[0]} row {position[1]} "
                f"before={result.before_covered_pixels}/{result.before_source_pixels} "
                f"after={result.after_covered_pixels}/{result.after_source_pixels} "
                f"moved={result.moved_pixels} secure_bottom={result.secure_bottom_page_y} "
                f"before_time={result.before_seconds:.3f}s after_time={result.after_seconds:.3f}s "
                f"exact_after={int(result.after_exact)}",
                flush=True,
            )

    print(
        f"provisional-boundary: attempted={attempted} exact_after={exact_after}/{attempted or 1} "
        f"moved_pixels={moved_total}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
