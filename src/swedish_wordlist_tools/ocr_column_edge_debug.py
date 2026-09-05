from __future__ import annotations

"""Render a narrow full-height pixel grid chosen directly from page ink.

The diagnostic deliberately ignores legacy column/row geometry:
1. threshold the full facsimile through the existing page pixel array,
2. remove the first (header) ink band at the top of the page,
3. descend to the first remaining horizontal scanline containing ink,
4. find that scanline's leftmost black pixel,
5. move 20 source pixels left and render 40 source pixels to the right,
6. show the complete page height as a nearest-neighbour pixel grid.

This is meant to make the page's real left-edge row structure inspectable.
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


def _page_ink(context: dict) -> list[bytearray]:
    owners = context["pixel_owners"]
    data = owners.data
    rows: list[bytearray] = []
    for y in range(owners.height):
        off = y * owners.width
        rows.append(bytearray(1 if data[off + x] != 0 else 0 for x in range(owners.width)))
    return rows


def _row_has_ink(row: bytearray) -> bool:
    return any(row)


def _first_ink_y(rows: list[bytearray], start: int = 0) -> int | None:
    for y in range(max(0, start), len(rows)):
        if _row_has_ink(rows[y]):
            return y
    return None


def _header_band_bottom(rows: list[bytearray], *, blank_run: int = 6) -> tuple[int, int]:
    """Return [top,bottom) for the first page-wide ink band.

    Glyphs can contain blank internal scanlines, so the band only ends after a
    small run of completely white page rows. This intentionally treats the
    little left glyph and the glyphs at the same height on the far right as one
    header band without knowing what they say.
    """
    top = _first_ink_y(rows)
    if top is None:
        raise RuntimeError("page contains no thresholded ink")

    blanks = 0
    for y in range(top, len(rows)):
        if _row_has_ink(rows[y]):
            blanks = 0
        else:
            blanks += 1
            if blanks >= blank_run:
                return top, y - blank_run + 1
    return top, len(rows)


def _whiten_band(rows: list[bytearray], top: int, bottom: int) -> None:
    for y in range(max(0, top), min(len(rows), bottom)):
        rows[y][:] = b"\x00" * len(rows[y])


def _first_text_scanline(rows: list[bytearray], start_y: int) -> tuple[int, int]:
    """Find first remaining horizontal scanline and its leftmost ink x."""
    y = _first_ink_y(rows, start_y)
    if y is None:
        raise RuntimeError("no ink remains below the removed header")
    row = rows[y]
    for x, value in enumerate(row):
        if value:
            return y, x
    raise AssertionError("ink row without a black pixel")


def _render_grid(
    rows: list[bytearray],
    *,
    source_left: int,
    source_width: int,
    cell: int,
    tick: int,
    header_top: int,
    header_bottom: int,
    first_text_y: int,
    first_text_x: int,
) -> Image.Image:
    height = len(rows)
    page_width = len(rows[0]) if rows else 0
    source_left = max(0, min(source_left, max(0, page_width - 1)))
    source_right = min(page_width, source_left + source_width)
    source_width = source_right - source_left

    ruler = 76
    top_pad = 28
    bottom_pad = 18
    grid_w = source_width * cell
    grid_h = height * cell
    out = Image.new("RGB", (ruler + grid_w + 12, top_pad + grid_h + bottom_pad), "white")
    draw = ImageDraw.Draw(out)
    font = _font(12)
    small = _font(10)
    gx = ruler
    gy = top_pad

    # Pixel cells: black/white source first, then thin grid lines over them.
    for y in range(height):
        for sx, x in enumerate(range(source_left, source_right)):
            if rows[y][x]:
                x0 = gx + sx * cell
                y0 = gy + y * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill="black")

    # A real grid is useful at this narrow width; horizontal every source pixel,
    # vertical every source pixel. Keep the lines light so ink remains obvious.
    grid_color = (210, 210, 210)
    for sx in range(source_width + 1):
        px = gx + sx * cell
        draw.line((px, gy, px, gy + grid_h), fill=grid_color, width=1)
    for y in range(height + 1):
        py = gy + y * cell
        draw.line((gx, py, gx + grid_w, py), fill=grid_color, width=1)

    # Strong y-axis every 20 source pixels (configurable).
    axis_x = gx - 8
    draw.line((axis_x, gy, axis_x, gy + grid_h), fill="black", width=1)
    for y in range(0, height + 1, max(1, tick)):
        py = gy + y * cell
        draw.line((axis_x - 7, py, axis_x, py), fill="black", width=1)
        label = str(y)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text((axis_x - 11 - (box[2] - box[0]), py - 7), label, fill="black", font=font)

    draw.text((gx, 3), f"x={source_left}..{source_right - 1}  ({source_width} px)", fill="black", font=font)
    draw.text(
        (gx, 16),
        f"header y={header_top}..{header_bottom - 1} whitened; first remaining ink=({first_text_x},{first_text_y})",
        fill="black",
        font=small,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find the first text reentry from the full page and render a 40-pixel full-height grid."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    # Retained only so old command lines do not fail; it is intentionally ignored.
    ap.add_argument("--column", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--width", type=int, default=40, help="source width to render; default 40")
    ap.add_argument("--left-pad", type=int, default=20, help="move this many source pixels left from first ink")
    ap.add_argument("--cell", type=int, default=6, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="y-axis label spacing in source pixels")
    ap.add_argument("--header-blank-run", type=int, default=6, help="white page rows ending the header band")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    rows = _page_ink(context)

    header_top, header_bottom = _header_band_bottom(rows, blank_run=max(1, args.header_blank_run))
    _whiten_band(rows, header_top, header_bottom)
    first_text_y, first_text_x = _first_text_scanline(rows, header_bottom)
    source_left = max(0, first_text_x - max(0, args.left_pad))

    image = _render_grid(
        rows,
        source_left=source_left,
        source_width=max(1, args.width),
        cell=max(2, args.cell),
        tick=max(1, args.tick),
        header_top=header_top,
        header_bottom=header_bottom,
        first_text_y=first_text_y,
        first_text_x=first_text_x,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(
        f"wrote {args.output}: page={args.page} header={header_top}..{header_bottom - 1} "
        f"first_remaining_ink=({first_text_x},{first_text_y}) "
        f"source_x={source_left}..{source_left + max(1, args.width) - 1}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
