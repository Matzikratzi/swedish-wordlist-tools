from __future__ import annotations

"""One-off page-4 experiment: insert a synthetic white separator band.

This deliberately does *not* change normal OCR behaviour. It builds page 4 in
exactly the usual way, then for one selected physical row paints a three-raster
white band straddling that row's current effective lower separator: one raster
line above the separator and two below it. The same pixels are cleared both in
the page image and in the page-wide ownership array so subsequent separator and
glyph analysis see the synthetic whitespace.
"""

import argparse
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_forward_page_scan import scan_page_forward
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_page_pixel_array import WHITE


def _paint_white_band(
    context: dict,
    *,
    column: int,
    row_index: int,
    height: int,
    start_delta: int,
) -> dict:
    columns = context["row_map"].get("columns") or []
    if not 0 <= column < len(columns):
        raise ValueError(f"column {column} out of range")
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        raise ValueError(f"row {row_index} out of range in column {column}")

    owners = context["pixel_owners"]
    entry = columns[column]
    content_left = (context.get("column_content_lefts") or {}).get(column)
    left = max(
        0,
        int(content_left if content_left is not None else entry.get("crop_left", entry.get("left", 0))),
    )
    right = min(
        owners.width,
        int(entry.get("crop_right", entry.get("right", owners.width))),
    )

    _box, effective_top, effective_bottom_before = page_editor._effective_owned_row_box(
        context, column, row_index, left, right, pad_y=0
    )
    band_top = int(effective_bottom_before) + int(start_delta)
    band_bottom = min(owners.height, band_top + int(height))
    if band_top < 0 or band_top >= owners.height or band_bottom <= band_top:
        raise ValueError(
            f"synthetic band outside page: top={band_top} bottom={band_bottom} height={owners.height}"
        )

    per_line_before: list[tuple[int, int]] = []
    cleared = 0
    for y in range(band_top, band_bottom):
        start = y * owners.width
        line_ink = 0
        for x in range(left, right):
            pos = start + x
            if owners.data[pos] != WHITE:
                line_ink += 1
                cleared += 1
                owners.data[pos] = WHITE
        per_line_before.append((y, line_ink))

    # Keep the displayed/source grayscale in sync with the ownership experiment.
    for image_key in ("page", "pixel_gray_page"):
        image = context.get(image_key)
        if image is None:
            continue
        pixels = image.load()
        for y in range(band_top, band_bottom):
            for x in range(left, right):
                pixels[x, y] = 255

    # Invalidate ownership-derived cached facts for the target and its neighbours.
    context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
    revisions = context.setdefault("pixel_owner_row_revisions", {})
    for pos in ((column, row_index - 1), (column, row_index), (column, row_index + 1)):
        if pos[1] < 0 or pos[1] >= len(rows):
            continue
        revisions[pos] = int(revisions.get(pos, 0)) + 1
    context.setdefault("known_glyph_ownership_done_pairs", set()).difference_update(
        {(column, row_index - 1), (column, row_index)}
    )

    _box_after, effective_top_after, effective_bottom_after = page_editor._effective_owned_row_box(
        context, column, row_index, left, right, pad_y=0
    )
    record = {
        "column": column,
        "row": row_index,
        "left": left,
        "right": right,
        "effective_top_before": int(effective_top),
        "effective_bottom_before": int(effective_bottom_before),
        "band_top": band_top,
        "band_bottom": band_bottom,
        "cleared_ink_pixels": cleared,
        "per_line_before": per_line_before,
        "effective_top_after": int(effective_top_after),
        "effective_bottom_after": int(effective_bottom_after),
    }
    print(
        "white-band: "
        f"page={context['page_number']} column={column} row={row_index} "
        f"upper_boundary={record['effective_top_before']} "
        f"old_lower_boundary={record['effective_bottom_before']} "
        f"band=[{band_top},{band_bottom}) start_delta={start_delta} height={height} "
        f"line_ink={per_line_before} cleared_ink={cleared} "
        f"new_lower_boundary={record['effective_bottom_after']}",
        flush=True,
    )
    return record


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Page-4-only OCR experiment with a synthetic 3-pixel white band across the current row boundary."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=4)
    ap.add_argument("--column", type=int, default=1)
    ap.add_argument("--row", type=int, default=23)
    ap.add_argument(
        "--band-start-delta",
        type=int,
        default=-1,
        help="band start relative to the current effective lower boundary; default -1 gives one line above and two below",
    )
    ap.add_argument("--band-height", type=int, default=3)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--boundary-radius", type=int, default=6)
    args = ap.parse_args()

    if args.page != 4:
        raise ValueError("this experiment is intentionally restricted to page 4")
    if args.band_height < 1:
        raise ValueError("--band-height must be >= 1")

    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    _paint_white_band(
        context,
        column=args.column,
        row_index=args.row,
        height=args.band_height,
        start_delta=args.band_start_delta,
    )

    started = perf_counter()
    fast_rows, fallback_rows = scan_page_forward(
        context, models, boundary_radius=args.boundary_radius
    )
    wall = perf_counter() - started

    fast_by_pos = {(row.column, row.row): row for row in fast_rows}
    fallback_by_pos = {(row.column, row.row): row for row in fallback_rows}
    key = (args.column, args.row)
    target_fast = fast_by_pos.get(key)
    target_fallback = fallback_by_pos.get(key)
    if target_fast is None:
        raise RuntimeError(f"target row {key} was not scanned")

    final_exact = bool(target_fast.exact or (target_fallback and target_fallback.exact))
    path = "fast" if target_fast.exact else "fallback"
    target_time = float(target_fast.elapsed) + (
        float(target_fallback.elapsed) if target_fallback is not None else 0.0
    )
    text = target_fallback.text if target_fallback is not None else target_fast.text
    print(
        "white-band-target: "
        f"page={args.page} column={args.column} row={args.row} "
        f"path={path} final_exact={final_exact} time={target_time:.3f}s text={text!r}",
        flush=True,
    )
    print(
        "white-band-page: "
        f"page={args.page} rows={len(fast_rows)} fast_exact={sum(r.exact for r in fast_rows)}/{len(fast_rows)} "
        f"fallback={len(fallback_rows)} final_exact={sum(r.exact for r in fast_rows) + sum(r.exact for r in fallback_rows)}/{len(fast_rows)} "
        f"scan_wall={wall:.3f}s",
        flush=True,
    )
    return 0 if final_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
