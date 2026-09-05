from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery."""

import argparse
from pathlib import Path

from PIL import ImageDraw

from . import ocr_page_cached_fast_path as cached
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_sequential_raw_page_rows_headwordfast as sequential
from .ocr_column_edge_debug import _render_grid
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_page1_layout_debug import _load_thresholded_page, detect_page1_layout_details


GRID_LEFT_PAD = 120
GRID_TOP_PAD = 40


def _install_page1_raw_layout(context: dict, jsonl: Path, threshold: int) -> None:
    """Install absolute raw-pixel column bounds and row-0 search starts for page 1."""
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


def _row_start_probe_pixel(context: dict, column: int, cache, row: int) -> tuple[int, int] | None:
    """Reproduce the scanner's x-first start probe and return its source pixel."""
    initial_border = (context.get("raw_page_initial_border_cache") or {}).get(column)
    if initial_border is None:
        return None

    if row == 0:
        search_from = int(initial_border) + 1
    else:
        search_from = int(cache[row - 1].border)
    left, right = _column_bounds_for_debug(context, column)
    search_limit = min(
        context["pixel_owners"].height,
        search_from + sequential.START_SEARCH_HEIGHT,
    )
    x = sequential._scanner._x_first_ink_x(
        context["raw_page_pixels"],
        search_from=search_from,
        search_limit=search_limit,
        left=left,
        right=right,
        include_homonym=True,
    )
    if x is None:
        return None
    ys = [
        y
        for y in range(search_from, search_limit)
        if (x, y) in context["raw_page_pixels"]
    ]
    if not ys:
        return None
    return x, min(ys)


def _draw_debug_image(
    context: dict,
    column: int,
    cache,
    target_row: int,
    output: Path,
) -> None:
    image = _render_grid(context["pixel_owners"]).convert("RGB")
    draw = ImageDraw.Draw(image)
    left, right = _column_bounds_for_debug(context, column)

    for row, item in enumerate(cache):
        y_baseline = GRID_TOP_PAD + item.baseline
        y_top = GRID_TOP_PAD + item.debug_top
        y_border = GRID_TOP_PAD + item.border
        x_left = GRID_LEFT_PAD + left
        x_right = GRID_LEFT_PAD + right - 1
        draw.line((x_left, y_baseline, x_right, y_baseline), fill=(0, 0, 255), width=1)
        draw.line((x_left, y_top, x_right, y_top), fill=(255, 165, 0), width=1)
        draw.line((x_left, y_border, x_right, y_border), fill=(0, 160, 0), width=1)

        probe = _row_start_probe_pixel(context, column, cache, row)
        if probe is not None:
            px, py = probe
            draw.line(
                (
                    GRID_LEFT_PAD + px,
                    GRID_TOP_PAD + py,
                    GRID_LEFT_PAD + px,
                    GRID_TOP_PAD + py + 9,
                ),
                fill=(255, 0, 0),
                width=1,
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--facit", type=Path, required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--column", type=int, required=True)
    parser.add_argument("--row", type=int, required=True)
    parser.add_argument("--threshold", type=int, default=200)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="overview PNG; defaults to /tmp/saol14-pageN-cC-raw-baselines.png",
    )
    args = parser.parse_args(argv)

    context = page_editor.load_page_context(args.jsonl, args.page, args.threshold)
    if args.page == 1:
        _install_page1_raw_layout(context, args.jsonl, args.threshold)

    models = load_facit_with_typography(args.facit)
    cache = sequential.ensure_row_cached(context, args.column, args.row, models)

    output = args.output or Path(
        f"/tmp/saol14-page{args.page}-c{args.column}-raw-baselines.png"
    )
    for row, item in enumerate(cache):
        probe = _row_start_probe_pixel(context, args.column, cache, row)
        marker = " <-- target" if row == args.row else ""
        probe_text = f" probe={probe}" if probe is not None else ""
        print(
            f"raw-page-row: row={row:03d} debug_top={item.debug_top} "
            f"start_x={item.start_x} baseline={item.baseline} border={item.border} "
            f"glyphs={item.matched_glyphs} pixels={item.matched_pixels} "
            f"right={item.matched_right}{probe_text}{marker}"
        )
        row_output = output.with_name(
            f"{output.stem}-row{row:03d}{output.suffix}"
        )
        _draw_debug_image(context, args.column, cache[: row + 1], row, row_output)
        print(f"raw-page-debug-image: {row_output}")

    _draw_debug_image(context, args.column, cache, args.row, output)
    print(
        f"raw-page-sequential: page={args.page} column={args.column} "
        f"target_row={args.row} cached_rows={len(cache)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
