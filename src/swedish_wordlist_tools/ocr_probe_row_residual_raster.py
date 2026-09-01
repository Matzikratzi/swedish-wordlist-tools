from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact
from .ocr_row_map_words import _owned_row_crop, _persistent_left_rule_x, _row_crop_box


def component_pixels(unmatched: set[tuple[int, int]], component: dict) -> set[tuple[int, int]]:
    left = int(component["left"])
    top = int(component["top"])
    right = int(component["right"])
    bottom = int(component["bottom"])
    return {
        (x, y)
        for x, y in unmatched
        if left <= x < right and top <= y < bottom
    }


def render_component_raster(
    pixels: set[tuple[int, int]],
    *,
    pad: int = 0,
    ink: str = "##",
    blank: str = "  ",
) -> str:
    if not pixels:
        return ""
    min_x = min(x for x, _y in pixels) - pad
    max_x = max(x for x, _y in pixels) + pad
    min_y = min(y for _x, y in pixels) - pad
    max_y = max(y for _x, y in pixels) + pad
    return "\n".join(
        "".join(ink if (x, y) in pixels else blank for x in range(min_x, max_x + 1))
        for y in range(min_y, max_y + 1)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Print unmatched exact-row ink components as terminal rasters.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, choices=(0, 1, 2), required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--pad", type=int, default=1)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    row_map = segment_page_rows(page, threshold=args.threshold)
    column_entry = row_map["columns"][args.column]
    rows = column_entry.get("rows") or []
    if not 0 <= args.row < len(rows):
        raise SystemExit(f"row {args.row} out of range; column {args.column} has {len(rows)} rows")
    row = rows[args.row]
    rule_x = _persistent_left_rule_x(page, column_entry, threshold=args.threshold)
    content_left = rule_x + 2 if rule_x is not None else None
    box = _row_crop_box(
        row,
        column=args.column,
        page_width=page.width,
        page_height=page.height,
        pad_y=1,
        left_override=content_left,
    )
    crop, removed_neighbor_pixels = _owned_row_crop(page, row, box, threshold=args.threshold)
    models = load_facit(args.facit)
    result = analyse_row_exact(crop, models, threshold=args.threshold)
    selected = result["selected"]
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    unmatched = result["ink"] - covered

    print(
        f"page={args.page} column={args.column} row={args.row} "
        f"unmatched={len(unmatched)} components={len(result['unmatched_components'])} "
        f"removed_neighbor_pixels={removed_neighbor_pixels}"
    )
    for index, item in enumerate(result["unmatched_components"]):
        page_left = box[0] + item["left"]
        page_right = box[0] + item["right"] - 1
        page_top = box[1] + item["top"]
        page_bottom = box[1] + item["bottom"] - 1
        pixels = component_pixels(unmatched, item)
        print(
            f"\nU{index:02d} x={page_left}..{page_right} y={page_top}..{page_bottom} "
            f"w={item['width']} h={item['height']} px={item['pixels']}"
        )
        print(render_component_raster(pixels, pad=args.pad))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
