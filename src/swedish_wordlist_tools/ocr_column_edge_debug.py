from __future__ import annotations

"""Render raw SAOL facsimile page pixels as an absolute-coordinate grid.

Coordinates are always source-PNG coordinates. No row/column geometry,
ownership, header removal, or rectangle masking is used. The default view is
the absolute source interval x=45..250, directly comparable with OCR diagnostics.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast

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


def _render_grid(page: Image.Image, *, source_left: int, source_right: int, cell: int, y_tick: int, x_tick: int) -> Image.Image:
    left = max(0, min(int(source_left), page.width - 1))
    right_inclusive = max(left, min(int(source_right), page.width - 1))
    right = right_inclusive + 1
    width = right - left
    height = page.height
    cell = max(2, cell)
    y_tick = max(1, y_tick)
    x_tick = max(1, x_tick)

    ruler_w = 120
    top_pad = 40
    right_pad = 72
    bottom_pad = 12
    grid_w = width * cell
    grid_h = height * cell
    out = Image.new("RGB", (ruler_w + grid_w + right_pad, top_pad + grid_h + bottom_pad), "white")
    draw = ImageDraw.Draw(out)
    axis_font = _font(24)
    gx = ruler_w
    gy = top_pad
    pix = page.load()

    for y in range(height):
        for source_x in range(left, right):
            if pix[source_x, y] == 0:
                display_x = source_x - left
                x0 = gx + display_x * cell
                y0 = gy + y * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill="black")

    grid_color = (210, 210, 210)
    for display_x in range(width + 1):
        px = gx + display_x * cell
        draw.line((px, gy, px, gy + grid_h), fill=grid_color, width=1)
    for y in range(height + 1):
        py = gy + y * cell
        draw.line((gx, py, gx + grid_w, py), fill=grid_color, width=1)

    axis_x = gx - 8
    draw.line((axis_x, gy, axis_x, gy + grid_h), fill="black", width=1)
    for source_y in range(0, height + 1, y_tick):
        py = gy + source_y * cell
        draw.line((axis_x - 7, py, axis_x, py), fill="black", width=1)
        label = str(source_y)
        box = draw.textbbox((0, 0), label, font=axis_font)
        text_h = box[3] - box[1]
        draw.text((axis_x - 14 - (box[2] - box[0]), py - text_h // 2), label, fill="black", font=axis_font)

    first_x_tick = ((left + x_tick - 1) // x_tick) * x_tick
    x_positions = list(range(first_x_tick, right, x_tick))
    if left not in x_positions:
        x_positions.insert(0, left)

    for source_y in range(0, height, 10):
        py = gy + source_y * cell
        draw.line((gx, py, gx + grid_w, py), fill="black", width=1)
        for source_x in x_positions:
            px = gx + (source_x - left) * cell
            draw.line((px, py - 7, px, py + 7), fill="black", width=1)

    numbered_y = 50
    if 0 <= numbered_y < height:
        py = gy + numbered_y * cell
        for source_x in x_positions:
            px = gx + (source_x - left) * cell
            label = str(source_x)
            box = draw.textbbox((0, 0), label, font=axis_font)
            text_w = box[2] - box[0]
            draw.rectangle((px - text_w // 2 - 2, py - 31, px + text_w // 2 + 2, py - 7), fill="white")
            draw.text((px - text_w // 2, py - 31), label, fill="black", font=axis_font)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render raw page pixels over an absolute source-PNG x interval.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--left", type=int, default=45, help="absolute source x of first displayed pixel; default 45")
    ap.add_argument("--right", type=int, default=250, help="absolute source x of last displayed pixel, inclusive; default 250")
    ap.add_argument("--width", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--cell", type=int, default=5, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="absolute y-coordinate label spacing")
    ap.add_argument("--x-tick", type=int, default=10, help="absolute x tick spacing on horizontal rulers")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    left = max(0, min(args.left, page.width - 1))
    right = max(left, min(args.right, page.width - 1))
    image = _render_grid(page, source_left=left, source_right=right, cell=args.cell, y_tick=args.tick, x_tick=args.x_tick)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(
        f"wrote {args.output}: page={args.page} raw_source_size={page.width}x{page.height} "
        f"shown_absolute_x={left}..{right} absolute_y=0..{page.height - 1} "
        f"numbered_x_axis_y=50 x_tick={args.x_tick} threshold={args.threshold}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
