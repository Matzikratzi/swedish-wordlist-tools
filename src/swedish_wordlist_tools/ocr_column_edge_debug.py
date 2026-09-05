from __future__ import annotations

"""Render a narrow, full-height source strip from one SAOL column.

This is a deliberately static diagnostic view: real facsimile pixels, enlarged
like the HTML reviewer, with an explicit page-y ruler every 20 pixels.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import ocr_review_page_pixel_array_glyphs_html as page_editor


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Write a full-height, narrow source-pixel strip with a page-y ruler."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--width", type=int, default=30, help="source pixels from the column's left edge")
    ap.add_argument("--scale", type=int, default=4, help="display pixels per source pixel")
    ap.add_argument("--tick", type=int, default=20, help="y-axis tick spacing in source pixels")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    columns = context["row_map"]["columns"]
    if args.column < 0 or args.column >= len(columns):
        raise SystemExit(f"column out of range: {args.column}; available 0..{len(columns)-1}")
    entry = columns[args.column]
    owners = context["pixel_owners"]

    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    right_limit = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    right = min(right_limit, left + max(1, args.width))
    source_width = right - left
    source_height = owners.height

    # Reconstruct the thresholded source view directly from the page-wide pixel
    # array: zero is white, every non-zero ownership/unassigned value is black.
    strip = Image.new("L", (source_width, source_height), 255)
    pixels = strip.load()
    data = owners.data
    for y in range(source_height):
        offset = y * owners.width
        for sx, x in enumerate(range(left, right)):
            if data[offset + x] != 0:
                pixels[sx, y] = 0

    scale = max(1, args.scale)
    enlarged = strip.resize((source_width * scale, source_height * scale), Image.Resampling.NEAREST)
    ruler_width = 90
    margin_right = 16
    out = Image.new("RGB", (ruler_width + enlarged.width + margin_right, enlarged.height), "white")
    out.paste(enlarged.convert("RGB"), (ruler_width, 0))
    draw = ImageDraw.Draw(out)
    font = _font(13)
    axis_x = ruler_width - 8
    draw.line((axis_x, 0, axis_x, enlarged.height - 1), fill="black", width=1)

    tick = max(1, args.tick)
    for y in range(0, source_height, tick):
        py = y * scale
        draw.line((axis_x - 8, py, axis_x, py), fill="black", width=1)
        label = str(y)
        box = draw.textbbox((0, 0), label, font=font)
        text_w = box[2] - box[0]
        draw.text((axis_x - 12 - text_w, max(0, py - 7)), label, fill="black", font=font)

    # Mark the exact source x interval so the picture is self-describing.
    draw.text((ruler_width + 2, 2), f"x={left}..{right-1}", fill="black", font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.output)
    print(
        f"wrote {args.output}: page={args.page} column={args.column} "
        f"source_x={left}..{right-1} width={source_width} height={source_height} scale={scale}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
