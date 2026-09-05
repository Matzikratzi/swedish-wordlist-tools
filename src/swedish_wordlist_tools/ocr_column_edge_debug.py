from __future__ import annotations

"""Render the full raw SAOL facsimile page as an absolute-coordinate grid.

Coordinates are always source-PNG coordinates. The fixed debug rulers remain at
absolute x=45 and y=50. On page 1 we run the raw-pixel layout detector on a copy
of the page, draw column bounds in blue, and draw the detected left-column blotch
and resulting row-0 top in red while rendering untouched source pixels.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from .ocr_page1_layout_debug import BlotchRange, ColumnRange, detect_page1_layout_details

fast = ultrafast.fast


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _load_thresholded_page(jsonl: Path, page_number: int, threshold: int) -> Image.Image:
    source = fast.source_for_page(fast.read_jsonl(jsonl), page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = fast._load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    gray = page if page.mode == "L" else page.convert("L")
    return gray.point(lambda value: 0 if value < threshold else 255, mode="1").convert("L")


def _render_grid(
    page: Image.Image,
    *,
    cell: int,
    y_tick: int,
    x_tick: int,
    axis_x_source: int,
    numbered_y: int,
    row0_top: int | None = None,
    columns: list[ColumnRange] | None = None,
    blotch: BlotchRange | None = None,
) -> Image.Image:
    width = page.width
    height = page.height
    cell = max(2, cell)
    y_tick = max(1, y_tick)
    x_tick = max(1, x_tick)
    axis_x_source = max(0, min(int(axis_x_source), width - 1))

    left_pad = 120
    top_pad = 40
    right_pad = 72
    bottom_pad = 12
    grid_w = width * cell
    grid_h = height * cell
    out = Image.new("RGB", (left_pad + grid_w + right_pad, top_pad + grid_h + bottom_pad), "white")
    draw = ImageDraw.Draw(out)
    axis_font = _font(24)
    gx = left_pad
    gy = top_pad
    pix = page.load()

    for source_y in range(height):
        for source_x in range(width):
            if pix[source_x, source_y] == 0:
                x0 = gx + source_x * cell
                y0 = gy + source_y * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill="black")

    grid_color = (210, 210, 210)
    for source_x in range(width + 1):
        px = gx + source_x * cell
        draw.line((px, gy, px, gy + grid_h), fill=grid_color, width=1)
    for source_y in range(height + 1):
        py = gy + source_y * cell
        draw.line((gx, py, gx + grid_w, py), fill=grid_color, width=1)

    axis_px = gx + axis_x_source * cell
    draw.line((axis_px, gy, axis_px, gy + grid_h), fill="black", width=1)
    for source_y in range(0, height + 1, y_tick):
        py = gy + source_y * cell
        draw.line((axis_px - 7, py, axis_px, py), fill="black", width=1)
        label = str(source_y)
        box = draw.textbbox((0, 0), label, font=axis_font)
        text_h = box[3] - box[1]
        draw.rectangle((axis_px - 20 - (box[2] - box[0]), py - text_h // 2 - 2, axis_px - 10, py + text_h // 2 + 2), fill="white")
        draw.text((axis_px - 14 - (box[2] - box[0]), py - text_h // 2), label, fill="black", font=axis_font)

    x_positions = list(range(0, width, x_tick))
    for source_y in range(0, height, 10):
        py = gy + source_y * cell
        draw.line((gx, py, gx + grid_w, py), fill="black", width=1)
        for source_x in x_positions:
            px = gx + source_x * cell
            draw.line((px, py - 7, px, py + 7), fill="black", width=1)

    if 0 <= numbered_y < height:
        py = gy + numbered_y * cell
        for source_x in x_positions:
            px = gx + source_x * cell
            label = str(source_x)
            box = draw.textbbox((0, 0), label, font=axis_font)
            text_w = box[2] - box[0]
            draw.rectangle((px - text_w // 2 - 2, py - 31, px + text_w // 2 + 2, py - 7), fill="white")
            draw.text((px - text_w // 2, py - 31), label, fill="black", font=axis_font)

    blue = (0, 90, 255)
    for column in columns or []:
        for source_x in (column.left, column.right):
            px = gx + source_x * cell
            draw.line((px, gy, px, gy + grid_h), fill=blue, width=3)

    red = (220, 0, 0)
    if blotch is not None:
        x0 = gx + blotch.left * cell
        x1 = gx + blotch.run_right * cell
        y0 = gy + blotch.top * cell
        y1 = gy + (blotch.bottom + 1) * cell
        draw.rectangle((x0, y0, x1, y1), outline=red, width=3)
        draw.line((x0, y0, x0, y1), fill=red, width=5)

    if row0_top is not None:
        py = gy + row0_top * cell
        if columns:
            x0 = gx + columns[0].left * cell
            x1 = gx + columns[0].right * cell
        else:
            x0 = gx
            x1 = gx + grid_w
        draw.line((x0, py, x1, py), fill=red, width=4)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the full raw page with fixed rulers and detected page-1 margins.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--left", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--right", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--width", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--cell", type=int, default=5, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="absolute y-coordinate label spacing")
    ap.add_argument("--x-tick", type=int, default=10, help="absolute x tick spacing on horizontal rulers")
    ap.add_argument("--axis-x", type=int, default=45, help="absolute source x of vertical y-axis; default 45")
    ap.add_argument("--axis-y", type=int, default=50, help="absolute source y of numbered x-axis; default 50")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    row0_top = None
    columns: list[ColumnRange] = []
    blotch = None
    if args.page == 1:
        layout_page = page.copy()
        layout = detect_page1_layout_details(layout_page)
        row0_top = layout.row0_top
        columns = layout.columns
        blotch = layout.blotch

    image = _render_grid(
        page,
        cell=args.cell,
        y_tick=args.tick,
        x_tick=args.x_tick,
        axis_x_source=args.axis_x,
        numbered_y=args.axis_y,
        row0_top=row0_top,
        columns=columns,
        blotch=blotch,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)

    print(
        f"wrote {args.output}: page={args.page} raw_source_size={page.width}x{page.height} "
        f"shown_absolute_x=0..{page.width - 1} absolute_y=0..{page.height - 1} "
        f"y_axis_x={args.axis_x} numbered_x_axis_y={args.axis_y} x_tick={args.x_tick} threshold={args.threshold}"
    )
    if row0_top is not None:
        print(f"overlay: row0_top={row0_top}")
        if blotch is None:
            print("overlay: blotch=none")
        else:
            print(
                f"overlay: blotch top={blotch.top} left={blotch.left} run_right={blotch.run_right} "
                f"bottom={blotch.bottom}"
            )
        for column in columns:
            print(
                f"overlay: column={column.index + 1} left={column.left} right={column.right} "
                f"gutter={column.gutter_left}..{column.gutter_right}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
