from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def render_pixel_grid(
    jsonl: Path,
    *,
    page_number: int,
    threshold: int = 210,
    scale: int = 3,
    grid_step: int = 10,
    label_step: int = 50,
    output: Path | None = None,
) -> Path:
    context = build_page_context_pixel_array(jsonl, page_number, threshold)
    gray = context["pixel_gray_page"]

    # Use exactly the same threshold convention as OCR: every source pixel is
    # either solid black or solid white before scaling. NEAREST keeps each
    # original pixel as a visibly square scale x scale block.
    binary = gray.point(lambda value: 0 if value < threshold else 255, mode="L")

    src_w, src_h = binary.size
    scaled = binary.resize((src_w * scale, src_h * scale), Image.Resampling.NEAREST).convert("RGB")

    margin_left = 46
    margin_top = 34
    margin_right = 16
    margin_bottom = 16
    canvas = Image.new(
        "RGB",
        (margin_left + scaled.width + margin_right, margin_top + scaled.height + margin_bottom),
        "white",
    )
    canvas.paste(scaled, (margin_left, margin_top))

    draw = ImageDraw.Draw(canvas)
    font = _load_font(max(9, 3 * scale))

    x0 = margin_left
    y0 = margin_top
    x1 = x0 + scaled.width
    y1 = y0 + scaled.height

    # Fine grid every grid_step source pixels; stronger line every label_step.
    for x in range(0, src_w + 1, grid_step):
        px = x0 + x * scale
        if x % label_step == 0:
            fill = (145, 145, 145)
            width = max(1, scale // 2)
        else:
            fill = (210, 210, 210)
            width = 1
        draw.line((px, y0, px, y1), fill=fill, width=width)

    for y in range(0, src_h + 1, grid_step):
        py = y0 + y * scale
        if y % label_step == 0:
            fill = (145, 145, 145)
            width = max(1, scale // 2)
        else:
            fill = (210, 210, 210)
            width = 1
        draw.line((x0, py, x1, py), fill=fill, width=width)

    # Coordinate labels every label_step original pixels.
    for x in range(0, src_w + 1, label_step):
        px = x0 + x * scale
        text = str(x)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((px - tw / 2, 3), text, fill="black", font=font)

    for y in range(0, src_h + 1, label_step):
        py = y0 + y * scale
        text = str(y)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((margin_left - tw - 5, py - th / 2), text, fill="black", font=font)

    if output is None:
        output = Path(f"saol14-page{page_number}-pixel-grid.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render a whole SAOL page as thresholded square pixels with a coordinate grid."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--grid-step", type=int, default=10)
    ap.add_argument("--label-step", type=int, default=50)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    output = render_pixel_grid(
        args.jsonl,
        page_number=args.page,
        threshold=args.threshold,
        scale=args.scale,
        grid_step=args.grid_step,
        label_step=args.label_step,
        output=args.output,
    )
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
