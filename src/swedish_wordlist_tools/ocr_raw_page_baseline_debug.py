from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery."""

import argparse
from pathlib import Path

from . import ocr_page_cached_fast_path as cached
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_sequential_raw_page_rows import ensure_row_cached


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Walk a SAOL column from row 0 and cache discovered raw-page baselines."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True, help="target discovered row; rows 0..N are scanned/cached")
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    cached.bind_page_candidates(context, models)

    cache = ensure_row_cached(context, args.column, args.row, models)
    print(
        f"raw-page-sequential: page={args.page} column={args.column} "
        f"target_row={args.row} cached_rows={len(cache)}"
    )
    for entry in cache:
        marker = " <-- target" if entry.row == args.row else ""
        print(
            f"  row={entry.row:03d} top={entry.row_top} "
            f"temp_bottom={entry.provisional_bottom} baseline={entry.baseline} "
            f"final_bottom={entry.final_bottom} next_search_y={entry.next_search_y} "
            f"glyphs={entry.matched_glyphs} pixels={entry.matched_pixels} "
            f"right={entry.matched_right}{marker}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
