from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery."""

import argparse
from pathlib import Path

from . import ocr_page_cached_fast_path as cached
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_sequential_raw_page_rows as sequential
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_page1_layout_debug import _load_thresholded_page, detect_page1_layout_details


def _install_page1_raw_layout(context: dict, jsonl: Path, threshold: int) -> None:
    """Install absolute raw-pixel column bounds and row-0 tops for page 1."""
    layout_page = _load_thresholded_page(jsonl, 1, threshold)
    layout = detect_page1_layout_details(layout_page)
    context["raw_page_column_layout"] = {
        column.index + 1: {
            "left": column.left,
            "right": column.right,
            "row0_top": row0_top,
            "bottom": context["pixel_owners"].height,
        }
        for column, row0_top in zip(layout.columns, layout.row0_tops)
    }
    context["raw_page_layout_source"] = "page1-raw-pixels"


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

    if args.page == 1:
        # Page 1 is known to start every headword row with an a/A variant.  For
        # this diagnostic path, use the six exact bold variants as the cheap
        # baseline seed.  This avoids assuming that an accented glyph is
        # geometrically equal to an unaccented a plus separate accent pixels.
        sequential.PAGE1_BASE_LABELS = sequential.PAGE1_EXACT_LABELS
        _install_page1_raw_layout(context, args.jsonl, args.threshold)
        raw_column = context["raw_page_column_layout"][args.column]
        print(
            f"raw-page-layout: source={context['raw_page_layout_source']} "
            f"column={args.column} left={raw_column['left']} right={raw_column['right']} "
            f"row0_top={raw_column['row0_top']}"
        )
        print(
            "raw-page-layout: page1-start-probe=bold:a,á,à,A,Á,À"
        )

    cache = sequential.ensure_row_cached(context, args.column, args.row, models)
    print(
        f"raw-page-sequential: page={args.page} column={args.column} "
        f"target_row={args.row} cached_rows={len(cache)}"
    )
    for entry in cache:
        marker = " <-- target" if entry.row == args.row else ""
        print(
            f"  row={entry.row:03d} top={entry.row_top} start_x={entry.start_x} "
            f"temp_bottom={entry.provisional_bottom} baseline={entry.baseline} "
            f"final_bottom={entry.final_bottom} next_search_y={entry.next_search_y} "
            f"glyphs={entry.matched_glyphs} pixels={entry.matched_pixels} "
            f"right={entry.matched_right}{marker}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
