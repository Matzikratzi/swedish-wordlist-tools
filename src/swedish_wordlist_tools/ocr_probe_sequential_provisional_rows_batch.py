from __future__ import annotations

"""Batch benchmark for sequential provisional row ownership."""

import argparse
from pathlib import Path

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_probe_sequential_provisional_rows import process_column_sequentially
from .ocr_review_page_pixel_array_shared import build_page_context_pixel_array


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Process each column top-down, carrying unmatched lower ink into the next row."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--print-seconds",
        type=float,
        default=0.5,
        help="print non-exact/moved/incoming rows, plus rows whose first analysis takes at least this long; 0 prints all rows",
    )
    args = ap.parse_args()
    if args.print_seconds < 0:
        raise ValueError("--print-seconds must be >= 0")

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    rows_total = 0
    exact_before = 0
    exact_after = 0
    rescued = 0
    regressed = 0
    moved_total = 0
    incoming_total = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        print(f"sequential-boundary: page {page}: {len(context['positions'])} rows", flush=True)

        for column, column_entry in enumerate(context["row_map"].get("columns") or []):
            results = process_column_sequentially(context, column, models)
            for result in results:
                rows_total += 1
                exact_before += int(result.before_exact)
                exact_after += int(result.after_exact)
                rescued += int((not result.before_exact) and result.after_exact)
                regressed += int(result.before_exact and not result.after_exact)
                moved_total += result.moved_pixels
                incoming_total += result.incoming_pixels

                should_print = (
                    args.print_seconds == 0
                    or result.before_seconds >= args.print_seconds
                    or result.moved_pixels > 0
                    or result.incoming_pixels > 0
                    or not result.after_exact
                )
                if not should_print:
                    continue
                print(
                    f"sequential-boundary: page {page} column {column} row {result.position[1]} "
                    f"incoming={result.incoming_pixels} moved={result.moved_pixels} "
                    f"before={result.before_covered_pixels}/{result.before_source_pixels} "
                    f"after={result.after_covered_pixels}/{result.after_source_pixels} "
                    f"secure_bottom={result.secure_bottom_page_y} "
                    f"before_time={result.before_seconds:.3f}s after_time={result.after_seconds:.3f}s "
                    f"exact={int(result.before_exact)}->{int(result.after_exact)}",
                    flush=True,
                )

    print(
        "sequential-boundary: "
        f"rows={rows_total} exact_before={exact_before}/{rows_total or 1} "
        f"exact_after={exact_after}/{rows_total or 1} rescued={rescued} regressed={regressed} "
        f"moved_pixels={moved_total} incoming_pixels={incoming_total}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
