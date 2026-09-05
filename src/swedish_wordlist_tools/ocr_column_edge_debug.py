from __future__ import annotations

"""Render an absolute-x strip of raw SAOL facsimile page pixels as a grid.

Coordinates are always source-PNG coordinates. No row/column geometry,
ownership, header removal, or rectangle masking is used. This makes debug
images directly comparable with later OCR diagnostics.
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


def _render_grid(page: Image.Image, *, source_left: int, source_width: int, cell: int, tick: int) -> Image.Image:
    left = max(0, min(int(source_left), page.width - 1))
    right = min(page.width, left + max(1, int(source_width)))
    width = right - left
    height = page.height
    cell = max(2, cell)
    tick = max(1, tick)

    ruler_w = 120
    top_pad = 40
    right_pad = 72  # previous 12 px plus requested 60 px
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

    # y labels are absolute source-PNG coordinates.
    axis_x = gx - 8
    draw.line((axis_x, gy, axis_x, gy + grid_h), fill="black", width=1)
    for source_y in range(0, height + 1, tick):
        py = gy + source_y * cell
        draw.line((axis_x - 7, py, axis_x, py), fill="black", width=1)
        label = str(source_y)
        box = draw.textbbox((0, 0), label, font=axis_font)
        text_h = box[3] - box[1]
        draw.text((axis_x - 14 - (box[2] - box[0]), py - text_h // 2), label, fill="black", font=axis_font)

    # x labels retain absolute source coordinates. Label every 20 pixels and
    # always label the exact left edge so cropped views remain unambiguous.
    label_xs = {left}
    first_multiple = ((left + tick - 1) // tick) * tick
    label_xs.update(range(first_multiple, right, tick))
    for source_x in sorted(label_xs):
        px = gx + (source_x - left) * cell
        draw.line((px, gy - 7, px, gy), fill="black", width=1)
        draw.text((px + 3, 3), str(source_x), fill="black", font=axis_font)

    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render raw page pixels using absolute source-PNG x/y coordinates."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--left", type=int, default=40, help="absolute source x of first displayed pixel; default 40")
    ap.add_argument("--width", type=int, default=60, help="number of source pixels to render; default 60 (x=40..99)")
    ap.add_argument("--cell", type=int, default=5, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="absolute coordinate label spacing")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    left = max(0, min(args.left, page.width - 1))
    right = min(page.width, left + max(1, args.width))
    image = _render_grid(page, source_left=left, source_width=args.width, cell=args.cell, tick=args.tick)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(
        f"wrote {args.output}: page={args.page} raw_source_size={page.width}x{page.height} "
        f"shown_absolute_x={left}..{right - 1} absolute_y=0..{page.height - 1} threshold={args.threshold}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
