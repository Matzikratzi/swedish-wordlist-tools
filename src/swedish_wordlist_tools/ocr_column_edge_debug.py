from __future__ import annotations

"""Render the raw leftmost source pixels of a SAOL facsimile page as a grid.

No row geometry, column geometry, ownership, header removal, or rectangle masking
is used. The source PNG is loaded directly, thresholded, and the leftmost N
source pixels are rendered for the full page height.
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


def _render_grid(page: Image.Image, *, source_width: int, cell: int, tick: int) -> Image.Image:
    width = min(max(1, source_width), page.width)
    height = page.height
    cell = max(2, cell)
    tick = max(1, tick)

    ruler_w = 72
    top_pad = 24
    right_pad = 12
    bottom_pad = 12
    grid_w = width * cell
    grid_h = height * cell

    out = Image.new("RGB", (ruler_w + grid_w + right_pad, top_pad + grid_h + bottom_pad), "white")
    draw = ImageDraw.Draw(out)
    font = _font(12)
    gx = ruler_w
    gy = top_pad
    pix = page.load()

    for y in range(height):
        for x in range(width):
            if pix[x, y] == 0:
                x0 = gx + x * cell
                y0 = gy + y * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill="black")

    grid_color = (210, 210, 210)
    for x in range(width + 1):
        px = gx + x * cell
        draw.line((px, gy, px, gy + grid_h), fill=grid_color, width=1)
    for y in range(height + 1):
        py = gy + y * cell
        draw.line((gx, py, gx + grid_w, py), fill=grid_color, width=1)

    axis_x = gx - 8
    draw.line((axis_x, gy, axis_x, gy + grid_h), fill="black", width=1)
    for y in range(0, height + 1, tick):
        py = gy + y * cell
        draw.line((axis_x - 7, py, axis_x, py), fill="black", width=1)
        label = str(y)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((axis_x - 11 - (box[2] - box[0]), py - 7), label, fill="black", font=font)

    draw.text((gx, 3), f"raw page pixels x=0..{width - 1}", fill="black", font=font)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render the raw leftmost page pixels for the full page height as a grid."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--width", type=int, default=100, help="number of leftmost source pixels to render")
    ap.add_argument("--cell", type=int, default=5, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="y-axis label spacing in source pixels")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    image = _render_grid(page, source_width=args.width, cell=args.cell, tick=args.tick)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    shown_width = min(max(1, args.width), page.width)
    print(
        f"wrote {args.output}: page={args.page} raw_source_size={page.width}x{page.height} "
        f"shown_x=0..{shown_width - 1} threshold={args.threshold}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
