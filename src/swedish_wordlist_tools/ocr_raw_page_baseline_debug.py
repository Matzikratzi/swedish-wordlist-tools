from __future__ import annotations

"""Command-line probe for sequential baseline-first raw-page discovery."""

import argparse
from pathlib import Path

from PIL import ImageDraw

from . import ocr_page_cached_fast_path as cached
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from . import ocr_sequential_raw_page_rows as sequential
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

    owners = context["pixel_owners"]
    left, right = _column_bounds_for_debug(context, column)
    x1 = min(right, left + sequential.FIRST_TEXT_SEARCH_WIDTH)
    y1 = min(owners.height, search_from + sequential.START_SEARCH_HEIGHT)
    data = owners.data
    for x in range(left, x1):
        for y in range(search_from, y1):
            if data[y * owners.width + x] != 0:
                return x, y
    return None


def _draw_snapshot(
    thresholded_page,
    context: dict,
    column: int,
    cache,
    output: Path,
    *,
    cell: int,
    y_tick: int,
    x_tick: int,
    axis_x: int,
    axis_y: int,
) -> None:
    """Draw absolute grid plus baseline, borders, diagnostic top and start probes."""
    image = _render_grid(
        thresholded_page,
        cell=cell,
        y_tick=y_tick,
        x_tick=x_tick,
        axis_x_source=axis_x,
        numbered_y=axis_y,
        row0_tops=None,
        columns=None,
    )
    draw = ImageDraw.Draw(image)
    left, right = _column_bounds_for_debug(context, column)
    x0 = GRID_LEFT_PAD + left * cell
    x1 = GRID_LEFT_PAD + right * cell
    label_x = x1 + 4

    initial_border = (context.get("raw_page_initial_border_cache") or {}).get(column)
    if initial_border is not None:
        y = GRID_TOP_PAD + initial_border * cell
        draw.line((x0, y, x1, y), fill=(120, 120, 120), width=1)
        draw.text((label_x, y - 5), f"initial_border={initial_border}", fill=(90, 90, 90))

    for entry in cache:
        top_y = GRID_TOP_PAD + entry.debug_top * cell
        baseline_y = GRID_TOP_PAD + entry.baseline * cell
        border_y = GRID_TOP_PAD + entry.border * cell
        draw.line((x0, top_y, x1, top_y), fill=(255, 0, 0), width=1)
        draw.line((x0, baseline_y, x1, baseline_y), fill=(0, 80, 255), width=1)
        draw.line((x0, border_y, x1, border_y), fill=(0, 170, 0), width=1)
        draw.text((label_x, top_y - 5), f"r{entry.row} debug_top={entry.debug_top}", fill=(255, 0, 0))
        draw.text((label_x, baseline_y - 5), f"base={entry.baseline}", fill=(0, 80, 255))
        draw.text((label_x, border_y - 5), f"border={entry.border}", fill=(0, 140, 0))

        probe = _row_start_probe_pixel(context, column, cache, entry.row)
        if probe is not None:
            probe_x, probe_y = probe
            px = GRID_LEFT_PAD + probe_x * cell + cell // 2
            py0 = GRID_TOP_PAD + probe_y * cell
            py1 = GRID_TOP_PAD + (probe_y + 10) * cell
            draw.line((px, py0, px, py1), fill=(255, 0, 0), width=2)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def _step_output(base: Path, row: int) -> Path:
    suffix = base.suffix or ".png"
    return base.with_name(f"{base.stem}-row{row:03d}{suffix}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Walk a SAOL column from row 0, cache rows and draw baseline/border as each row completes."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True, help="target discovered row; rows 0..N are scanned sequentially")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--cell", type=int, default=5, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="absolute y-coordinate label spacing")
    ap.add_argument("--x-tick", type=int, default=10, help="absolute x tick spacing on horizontal rulers")
    ap.add_argument("--axis-x", type=int, default=45, help="absolute source x of vertical y-axis")
    ap.add_argument("--axis-y", type=int, default=50, help="absolute source y of numbered x-axis")
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
            f"row0_search_from={raw_column['row0_top']}"
        )
        print("raw-page-layout: page1-start-probe=bold:a,á,à,A,Á,À")
    print("raw-page-layout: geometry=initial-border-then-previous-border")
    print("raw-page-layout: row-start=x-first upper-boundary..+14")
    print("raw-page-layout: start-probe-marker=red-vertical-10px")

    completed = []
    stopped_row: int | None = None
    stopped_reason: str | None = None

    for row_index in range(args.row + 1):
        try:
            cache = sequential.ensure_row_cached(context, args.column, row_index, models)
        except RuntimeError as exc:
            stopped_row = row_index
            stopped_reason = str(exc)
            if completed:
                _draw_snapshot(
                    thresholded_page, context, args.column, completed, output,
                    cell=args.cell, y_tick=args.tick, x_tick=args.x_tick,
                    axis_x=args.axis_x, axis_y=args.axis_y,
                )
                print(f"raw-page-debug-image: senaste färdiga rader sparade i {output}")
            print(f"raw-page-stop: row={row_index:03d} reason={exc}")
            break

        entry = cache[row_index]
        completed = list(cache)
        if row_index == 0:
            initial_border = context["raw_page_initial_border_cache"][args.column]
            print(f"raw-page-initial-border: column={args.column} border={initial_border}")
        probe = _row_start_probe_pixel(context, args.column, cache, row_index)
        probe_text = f" probe={probe}" if probe is not None else ""
        marker = " <-- target" if entry.row == args.row else ""
        print(
            f"raw-page-row: row={entry.row:03d} debug_top={entry.debug_top} "
            f"start_x={entry.start_x} baseline={entry.baseline} border={entry.border} "
            f"glyphs={entry.matched_glyphs} pixels={entry.matched_pixels} "
            f"right={entry.matched_right}{probe_text}{marker}"
        )
        step_path = _step_output(output, row_index)
        _draw_snapshot(
            thresholded_page, context, args.column, completed, step_path,
            cell=args.cell, y_tick=args.tick, x_tick=args.x_tick,
            axis_x=args.axis_x, axis_y=args.axis_y,
        )
        _draw_snapshot(
            thresholded_page, context, args.column, completed, output,
            cell=args.cell, y_tick=args.tick, x_tick=args.x_tick,
            axis_x=args.axis_x, axis_y=args.axis_y,
        )
        print(f"raw-page-debug-image: {step_path}")

    if stopped_row is None:
        print(
            f"raw-page-sequential: page={args.page} column={args.column} "
            f"target_row={args.row} cached_rows={len(completed)} output={output}"
        )
    else:
        print(
            f"raw-page-sequential: page={args.page} column={args.column} "
            f"target_row={args.row} cached_rows={len(completed)} stopped_row={stopped_row} "
            f"output={output}"
        )
        if stopped_reason:
            print(f"raw-page-sequential-stop-reason: {stopped_reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
