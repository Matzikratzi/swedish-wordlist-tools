from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_glyph_review_delete import load_facit_with_typography
from . import ocr_review_page_pixel_array_glyphs_html as review
from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from . import ocr_group_baseline_fallback as fallback
from . import ocr_page_cached_fast_path as page_fast


def _wrap(obj, name: str, timings: dict[str, list[float]]):
    original = getattr(obj, name)

    def wrapped(*args, **kwargs):
        started = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            timings[name].append(perf_counter() - started)

    setattr(obj, name, wrapped)
    return original


def main() -> int:
    ap = argparse.ArgumentParser(description="Trace the complete timing pipeline for one OCR row")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = review.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    timings: dict[str, list[float]] = defaultdict(list)

    # Row-level and ownership stages.
    _wrap(review, "_load_owned_row_state", timings)
    _wrap(review, "_ensure_known_glyph_ownership", timings)
    _wrap(review, "refine_known_glyph_ownership", timings)
    _wrap(review, "_assign_split_components_below_known_extent", timings)
    _wrap(review, "_auto_assign_isolated_descenders", timings)
    _wrap(review, "add_neighbor_row_raster", timings)

    # The parser path used by the page-byte-array loader.
    _wrap(review.fast, "analyse_row_exact", timings)
    _wrap(ultrafast, "analyse_row_exact_grouped_with_baseline_fallback", timings)
    _wrap(fallback, "_anchor_missing_baseline", timings)
    _wrap(fallback, "_select_at_baseline", timings)
    _wrap(page_fast, "_row_ink", timings)
    _wrap(page_fast, "_build_page_candidates", timings)
    _wrap(page_fast, "_bound_page_candidates", timings)
    _wrap(page_fast, "page_cached_prioritized_fast_exact_cover", timings)

    started = perf_counter()
    state = review.load_review_state_pixel_array(context, (args.column, args.row), models)
    total = perf_counter() - started

    print(
        f"target page={args.page} column={args.column} row={args.row} total={total:.6f}s "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )
    print(f"owner_revision={state.get('pixel_owner_revision')} row_revision={state.get('pixel_owner_row_revision')}")

    order = (
        "_load_owned_row_state",
        "analyse_row_exact",
        "analyse_row_exact_grouped_with_baseline_fallback",
        "_row_ink",
        "page_cached_prioritized_fast_exact_cover",
        "_bound_page_candidates",
        "_build_page_candidates",
        "_anchor_missing_baseline",
        "_select_at_baseline",
        "_ensure_known_glyph_ownership",
        "refine_known_glyph_ownership",
        "_assign_split_components_below_known_extent",
        "_auto_assign_isolated_descenders",
        "add_neighbor_row_raster",
    )
    for name in order:
        rows = timings.get(name, [])
        each = ",".join(f"{value:.6f}" for value in rows) if rows else "-"
        print(f"stage {name}: calls={len(rows)} total={sum(rows):.6f}s each={each}")

    # Non-overlapping top-level accounting. _load contains parser calls; ownership
    # and neighbor raster happen outside it in load_review_state_pixel_array().
    top_level = (
        sum(timings.get("_load_owned_row_state", []))
        + sum(timings.get("_ensure_known_glyph_ownership", []))
        + sum(timings.get("_assign_split_components_below_known_extent", []))
        + sum(timings.get("_auto_assign_isolated_descenders", []))
        + sum(timings.get("add_neighbor_row_raster", []))
    )
    print(f"top_level_accounted={top_level:.6f}s")
    print(f"top_level_unattributed={max(0.0, total-top_level):.6f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
