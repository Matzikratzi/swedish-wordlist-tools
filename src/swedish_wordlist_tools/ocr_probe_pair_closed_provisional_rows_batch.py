from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_probe_pair_closed_provisional_rows import process_column_pair_closed
from .ocr_review_page_pixel_array_shared import build_page_context_pixel_array


def main() -> int:
    ap = argparse.ArgumentParser(description="Strict pair-closed provisional row-boundary probe.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--print-seconds", type=float, default=0.5)
    args = ap.parse_args()

    pages = _selected_pages(
        _available_pages(args.jsonl), pages=args.pages,
        start_page=args.start_page, end_page=args.end_page,
    )
    models = load_facit_with_typography(args.facit)

    rows_total = 0
    proposals = 0
    committed_pairs = 0
    committed_pixels = 0
    rejected_upper_exact = 0

    for page in pages:
        context = build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        print(f"pair-closure: page {page}: {len(context['positions'])} rows", flush=True)
        for column in range(len(context["row_map"].get("columns") or [])):
            for result in process_column_pair_closed(context, column, models):
                rows_total += 1
                if result.proposed_pixels:
                    proposals += 1
                if result.committed:
                    committed_pairs += 1
                    committed_pixels += result.committed_pixels
                elif result.proposed_pixels and result.upper_after_exact and result.lower_after_exact is False:
                    rejected_upper_exact += 1

                interesting = (
                    result.proposed_pixels > 0
                    or result.upper_before_seconds >= args.print_seconds
                    or result.upper_after_seconds >= args.print_seconds
                )
                if not interesting:
                    continue
                lower = "-" if result.lower is None else str(result.lower[1])
                lower_ratio = "-"
                if result.lower_after_source is not None:
                    lower_ratio = f"{result.lower_after_covered}/{result.lower_after_source}"
                print(
                    f"pair-closure: page {page} column {result.upper[0]} row {result.upper[1]}/{lower} "
                    f"proposed={result.proposed_pixels} committed={result.committed_pixels} "
                    f"upper={result.upper_before_covered}/{result.upper_before_source}->"
                    f"{result.upper_after_covered}/{result.upper_after_source} "
                    f"lower={lower_ratio} "
                    f"exact={int(result.upper_before_exact)}->{int(result.upper_after_exact)} "
                    f"lower_exact={'-' if result.lower_after_exact is None else int(result.lower_after_exact)} "
                    f"commit={int(result.committed)} secure_bottom={result.secure_bottom_page_y} "
                    f"times={result.upper_before_seconds:.3f}/{result.upper_after_seconds:.3f}/{result.lower_after_seconds:.3f}s",
                    flush=True,
                )

    print(
        f"pair-closure: rows={rows_total} proposals={proposals} committed_pairs={committed_pairs} "
        f"committed_pixels={committed_pixels} rejected_upper_exact={rejected_upper_exact}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
