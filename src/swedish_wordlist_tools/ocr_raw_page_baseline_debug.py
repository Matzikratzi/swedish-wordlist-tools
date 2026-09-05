from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery."""

import argparse
from pathlib import Path

from PIL import ImageDraw

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


def _column_bounds_for_debug(context: dict, column: int) -> tuple[int, int]:
    raw_layout = context.get("raw_page_column_layout") or {}
    if column in raw_layout:
        entry = raw_layout[column]
        return int(entry["left"]), int(entry["right"])
    entry = context["row_map"]["columns"][column]
    return (
        int(entry.get("crop_left", entry.get("left", 0))),
        int(entry.get("crop_right", entry.get("right", context["pixel_owners"].width))),
    )


def _draw_snapshot(
    thresholded_page,
    context: dict,
    column: int,
    cache,
    output: Path,
) -> None:
    """Draw absolute row top, support baseline and half-open bottom."""
    image = thresholded_page.convert("RGB")
    draw = ImageDraw.Draw(image)
    left, right = _column_bounds_for_debug(context, column)
    label_x = min(image.width - 1, right + 4)

    for entry in cache:
        # top = red, support baseline = blue, final half-open bottom = green.
        draw.line((left, entry.row_top, right - 1, entry.row_top), fill=(255, 0, 0), width=1)
        draw.line((left, entry.baseline, right - 1, entry.baseline), fill=(0, 80, 255), width=1)
        draw.line((left, entry.final_bottom, right - 1, entry.final_bottom), fill=(0, 170, 0), width=1)
        draw.text((label_x, entry.row_top - 5), f"r{entry.row} top={entry.row_top}", fill=(255, 0, 0))
        draw.text((label_x, entry.baseline - 5), f"base={entry.baseline}", fill=(0, 80, 255))
        draw.text((label_x, entry.final_bottom - 5), f"bottom={entry.final_bottom}", fill=(0, 140, 0))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _step_output(base: Path, row: int) -> Path:
    suffix = base.suffix or ".png"
    return base.with_name(f"{base.stem}-row{row:03d}{suffix}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Walk a SAOL column from row 0, cache rows and draw boundaries as each row completes."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True, help="target discovered row; rows 0..N are scanned sequentially")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG base path; one snapshot is saved after every completed row",
    )
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    cached.bind_page_candidates(context, models)

    thresholded_page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    output = args.output or Path(
        f"/tmp/saol14-page{args.page}-c{args.column}-raw-baselines.png"
    )

    if args.page == 1:
        _install_page1_raw_layout(context, args.jsonl, args.threshold)
        raw_column = context["raw_page_column_layout"][args.column]
        print(
            f"raw-page-layout: source={context['raw_page_layout_source']} "
            f"column={args.column} left={raw_column['left']} right={raw_column['right']} "
            f"row0_top={raw_column['row0_top']}"
        )
        print("raw-page-layout: page1-start-probe=bold:a,á,à,A,Á,À")

    completed = []
    try:
        for row_index in range(args.row + 1):
            cache = sequential.ensure_row_cached(context, args.column, row_index, models)
            entry = cache[row_index]
            completed = list(cache)
            marker = " <-- target" if entry.row == args.row else ""
            print(
                f"raw-page-row: row={entry.row:03d} top={entry.row_top} "
                f"start_x={entry.start_x} temp_bottom={entry.provisional_bottom} "
                f"baseline={entry.baseline} final_bottom={entry.final_bottom} "
                f"glyphs={entry.matched_glyphs} pixels={entry.matched_pixels} "
                f"right={entry.matched_right}{marker}"
            )
            step_path = _step_output(output, row_index)
            _draw_snapshot(thresholded_page, context, args.column, completed, step_path)
            _draw_snapshot(thresholded_page, context, args.column, completed, output)
            print(f"raw-page-debug-image: {step_path}")
    except Exception:
        if completed:
            _draw_snapshot(thresholded_page, context, args.column, completed, output)
            print(f"raw-page-debug-image: senaste färdiga rader sparade i {output}")
        raise

    print(
        f"raw-page-sequential: page={args.page} column={args.column} "
        f"target_row={args.row} cached_rows={len(completed)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
