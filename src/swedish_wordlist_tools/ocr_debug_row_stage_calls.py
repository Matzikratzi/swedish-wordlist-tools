from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_glyph_review_delete import load_facit_with_typography
from . import ocr_review_page_pixel_array_glyphs_html as review


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
    ap = argparse.ArgumentParser(description="Trace non-exact-cover stages for one OCR row")
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

    # Functions referenced dynamically from the page-byte-array review layer.
    _wrap(review.fast, "residual_component_pixels", timings)
    _wrap(review.fast.legacy, "_png_data_uri", timings)
    _wrap(review.fast, "render_exact_text", timings)
    _wrap(review.fast, "render_exact_markup", timings)

    owners = context["pixel_owners"]
    _wrap(owners, "render_owner_crop", timings)
    _wrap(owners, "counts", timings)

    # Time the row-state constructor and the final diagnostic three-row raster separately.
    original_load = review._load_owned_row_state
    original_neighbor = review.add_neighbor_row_raster

    def timed_load(*a, **kw):
        started = perf_counter()
        try:
            return original_load(*a, **kw)
        finally:
            timings["_load_owned_row_state"].append(perf_counter() - started)

    def timed_neighbor(*a, **kw):
        started = perf_counter()
        try:
            return original_neighbor(*a, **kw)
        finally:
            timings["add_neighbor_row_raster"].append(perf_counter() - started)

    review._load_owned_row_state = timed_load
    review.add_neighbor_row_raster = timed_neighbor

    started = perf_counter()
    state = review.load_review_state_pixel_array(context, (args.column, args.row), models)
    total = perf_counter() - started

    print(
        f"target page={args.page} column={args.column} row={args.row} total={total:.6f}s "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )
    print(f"owner_revision={state.get('pixel_owner_revision')} row_revision={state.get('pixel_owner_row_revision')}")

    for name in (
        "_load_owned_row_state",
        "render_owner_crop",
        "residual_component_pixels",
        "_png_data_uri",
        "render_exact_text",
        "render_exact_markup",
        "counts",
        "add_neighbor_row_raster",
    ):
        rows = timings.get(name, [])
        print(
            f"stage {name}: calls={len(rows)} total={sum(rows):.6f}s "
            f"each=" + ",".join(f"{value:.6f}" for value in rows)
        )

    measured = sum(sum(rows) for name, rows in timings.items() if name in {
        "residual_component_pixels", "_png_data_uri", "render_exact_text",
        "render_exact_markup", "counts", "add_neighbor_row_raster"
    })
    print(f"selected_leaf_stage_time={measured:.6f}s")
    print(f"unattributed_vs_total={max(0.0, total-measured):.6f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
