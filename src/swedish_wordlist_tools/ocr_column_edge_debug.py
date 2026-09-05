from __future__ import annotations

"""Render a narrow full-height pixel grid chosen directly from page ink.

The diagnostic deliberately ignores legacy column/row geometry:
1. threshold the full facsimile through the existing page pixel array,
2. remove only the small connected components belonging to the top header,
3. descend to the first remaining horizontal scanline containing ink,
4. find that scanline's leftmost black pixel,
5. move 20 source pixels left and render 40 source pixels to the right,
6. show the complete page height as a source-pixel grid.
"""

import argparse
from collections import deque
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


def _components(rows: list[bytearray]) -> list[tuple[set[tuple[int, int]], tuple[int, int, int, int]]]:
    """Return 8-connected black components and half-open bounding boxes."""
    if not rows:
        return []
    height = len(rows)
    width = len(rows[0])
    seen: set[tuple[int, int]] = set()
    result = []
    for y in range(height):
        for x in range(width):
            if not rows[y][x] or (x, y) in seen:
                continue
            q = deque([(x, y)])
            seen.add((x, y))
            pixels: set[tuple[int, int]] = set()
            min_x = max_x = x
            min_y = max_y = y
            while q:
                px, py = q.popleft()
                pixels.add((px, py))
                min_x = min(min_x, px); max_x = max(max_x, px)
                min_y = min(min_y, py); max_y = max(max_y, py)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = px + dx, py + dy
                        if not (0 <= nx < width and 0 <= ny < height):
                            continue
                        if not rows[ny][nx] or (nx, ny) in seen:
                            continue
                        seen.add((nx, ny))
                        q.append((nx, ny))
            result.append((pixels, (min_x, min_y, max_x + 1, max_y + 1)))
    return result


def _remove_top_header_components(
    rows: list[bytearray], *, top_slack: int = 14, max_height: int = 24
) -> tuple[int, int, int]:
    """Whiten only small components sharing the page's very first y-band.

    This matches the actual SAOL header shape: a small glyph at the left and a
    handful of glyphs at roughly the same height on the far right. Unlike the
    previous page-row-band heuristic, dense dictionary text below cannot cause
    the header removal to grow down through the page.
    """
    first_y = _first_ink_y(rows)
    if first_y is None:
        raise RuntimeError("page contains no thresholded ink")

    selected = []
    for pixels, bbox in _components(rows):
        _left, top, _right, bottom = bbox
        height = bottom - top
        if top <= first_y + top_slack and height <= max_height:
            selected.append((pixels, bbox))

    if not selected:
        raise RuntimeError(f"no small top components found near y={first_y}")

    bottom = first_y
    for pixels, bbox in selected:
        bottom = max(bottom, bbox[3])
        for x, y in pixels:
            rows[y][x] = 0
    return first_y, bottom, len(selected)


def _first_text_scanline(rows: list[bytearray], start_y: int) -> tuple[int, int]:
    """Find first remaining horizontal scanline and its leftmost ink x."""
    y = _first_ink_y(rows, start_y)
    if y is None:
        raise RuntimeError("no ink remains below the removed top components")
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
    header_components: int,
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

    for y in range(height):
        for sx, x in enumerate(range(source_left, source_right)):
            if rows[y][x]:
                x0 = gx + sx * cell
                y0 = gy + y * cell
                draw.rectangle((x0, y0, x0 + cell - 1, y0 + cell - 1), fill="black")

    grid_color = (210, 210, 210)
    for sx in range(source_width + 1):
        px = gx + sx * cell
        draw.line((px, gy, px, gy + grid_h), fill=grid_color, width=1)
    for y in range(height + 1):
        py = gy + y * cell
        draw.line((gx, py, gx + grid_w, py), fill=grid_color, width=1)

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
        f"top components={header_components}, y={header_top}..{header_bottom - 1}; first remaining ink=({first_text_x},{first_text_y})",
        fill="black",
        font=small,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Remove the top header components, then render a 40-pixel full-height page grid."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--width", type=int, default=40, help="source width to render; default 40")
    ap.add_argument("--left-pad", type=int, default=20, help="move this many source pixels left from first ink")
    ap.add_argument("--cell", type=int, default=6, help="display pixels per source-pixel cell")
    ap.add_argument("--tick", type=int, default=20, help="y-axis label spacing in source pixels")
    ap.add_argument("--header-top-slack", type=int, default=14, help="max component top offset from first page ink")
    ap.add_argument("--header-max-height", type=int, default=24, help="largest component height considered header")
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    rows = _page_ink(context)

    header_top, header_bottom, header_components = _remove_top_header_components(
        rows,
        top_slack=max(0, args.header_top_slack),
        max_height=max(1, args.header_max_height),
    )
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
        header_components=header_components,
        first_text_y=first_text_y,
        first_text_x=first_text_x,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(
        f"wrote {args.output}: page={args.page} removed_top_components={header_components} "
        f"header_y={header_top}..{header_bottom - 1} first_remaining_ink=({first_text_x},{first_text_y}) "
        f"source_x={source_left}..{source_left + max(1, args.width) - 1}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
