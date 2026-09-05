from __future__ import annotations

"""Detect page-1 text top and three column x-ranges from raw facsimile pixels.

This deliberately uses only the thresholded source PNG and absolute source
coordinates. For page 1 we hard-code that y < 60 is irrelevant and whiten it
before any geometry is discovered.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast

fast = ultrafast.fast
PAGE1_IGNORE_ABOVE_Y = 60
MIN_GUTTER_WIDTH = 3
MIN_COLUMN_PROBE_WIDTH = 20


@dataclass(frozen=True)
class ColumnRange:
    index: int
    left: int
    # Absolute x boundary immediately to the right of the column text area.
    # In other words, this is the first white x column of the detected gutter,
    # not the last possible black x coordinate inside the column.
    right: int
    gutter_left: int
    gutter_right: int


def _load_thresholded_page(jsonl: Path, page_number: int, threshold: int) -> Image.Image:
    source = fast.source_for_page(fast.read_jsonl(jsonl), page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = fast._load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    gray = page if page.mode == "L" else page.convert("L")
    return gray.point(lambda value: 0 if value < threshold else 255, mode="1").convert("L")


def _blank_above(page: Image.Image, y: int) -> None:
    """Whiten all source pixels with absolute y < y, in-place."""
    pix = page.load()
    stop = max(0, min(int(y), page.height))
    for py in range(stop):
        for px in range(page.width):
            pix[px, py] = 255


def _first_ink_row(page: Image.Image, start_y: int) -> int:
    pix = page.load()
    for y in range(max(0, start_y), page.height):
        for x in range(page.width):
            if pix[x, y] == 0:
                return y
    raise RuntimeError(f"no black pixel found at or below y={start_y}")


def _first_ink_x_on_row(page: Image.Image, y: int, start_x: int = 0) -> int | None:
    """Return first absolute x containing ink on exactly source row y."""
    pix = page.load()
    if not (0 <= y < page.height):
        return None
    for x in range(max(0, start_x), page.width):
        if pix[x, y] == 0:
            return x
    return None


def _first_ink_y_in_column(page: Image.Image, x: int, start_y: int) -> int | None:
    """Return first absolute y containing ink in exactly source column x."""
    pix = page.load()
    if not (0 <= x < page.width):
        return None
    for y in range(max(0, start_y), page.height):
        if pix[x, y] == 0:
            return y
    return None


def _vertical_occupancy(page: Image.Image, top: int) -> list[bool]:
    """True for source x columns containing any black pixel at y >= top."""
    pix = page.load()
    occupied = [False] * page.width
    for x in range(page.width):
        for y in range(top, page.height):
            if pix[x, y] == 0:
                occupied[x] = True
                break
    return occupied


def _next_black_column(occupied: list[bool], start_x: int) -> int | None:
    for x in range(max(0, start_x), len(occupied)):
        if occupied[x]:
            return x
    return None


def _next_white_band(
    occupied: list[bool], start_x: int, *, min_width: int = MIN_GUTTER_WIDTH
) -> tuple[int, int] | None:
    """Return the next half-open run [left,right) of >= min_width white columns."""
    x = max(0, start_x)
    width = len(occupied)
    while x < width:
        if occupied[x]:
            x += 1
            continue
        left = x
        while x < width and not occupied[x]:
            x += 1
        if x - left >= min_width:
            return left, x
    return None


def detect_page1_layout(page: Image.Image) -> tuple[int, list[ColumnRange]]:
    _blank_above(page, PAGE1_IGNORE_ABOVE_Y)
    row0_top = _first_ink_row(page, PAGE1_IGNORE_ABOVE_Y)
    occupied = _vertical_occupancy(page, row0_top)

    # Important: the first column starts where the first actual row starts.
    # Looking for the first vertically occupied x column over the whole page can
    # be fooled by an isolated mark much farther down (page 1 has such material
    # near the far left). The row0-top pixel is the evidence we just established.
    first_left = _first_ink_x_on_row(page, row0_top)
    if first_left is None:
        raise RuntimeError(f"row0_top={row0_top} unexpectedly contains no black pixel")

    columns: list[ColumnRange] = []
    search_x = first_left
    for index in range(3):
        if index == 0:
            left = first_left
        else:
            left = _next_black_column(occupied, search_x)
        if left is None:
            raise RuntimeError(f"could not find start of column {index + 1} after x={search_x}")

        gutter = _next_white_band(
            occupied,
            left + MIN_COLUMN_PROBE_WIDTH,
            min_width=MIN_GUTTER_WIDTH,
        )
        if gutter is None:
            if index != 2:
                raise RuntimeError(f"could not find >= {MIN_GUTTER_WIDTH}px white gutter after column {index + 1}")
            columns.append(
                ColumnRange(
                    index=index,
                    left=left,
                    right=len(occupied),
                    gutter_left=len(occupied),
                    gutter_right=len(occupied),
                )
            )
            break

        gutter_left, gutter_right = gutter
        columns.append(
            ColumnRange(
                index=index,
                left=left,
                # The right boundary is the first white x of the gutter. Keeping
                # the boundary outside the text means a glyph may use every pixel
                # through x=gutter_left-1 without the blue boundary covering it.
                right=gutter_left,
                gutter_left=gutter_left,
                gutter_right=gutter_right - 1,
            )
        )
        search_x = gutter_right

    if len(columns) != 3:
        raise RuntimeError(f"expected 3 columns, found {len(columns)}")
    return row0_top, columns


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect page-1 row=0 top and three columns from raw source pixels.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    if args.page != 1:
        raise ValueError("this detector is intentionally hard-coded for page 1")

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    row0_top, columns = detect_page1_layout(page)

    # Reproduce the old mistake explicitly for diagnostics: scan all y>=row0_top
    # for the leftmost vertically occupied x and print the first actual pixel that
    # made that x occupied. This tells us exactly where a bogus early column start
    # such as x=19 came from.
    occupied = _vertical_occupancy(page, row0_top)
    old_left = _next_black_column(occupied, 0)
    if old_left is not None:
        old_y = _first_ink_y_in_column(page, old_left, row0_top)
        print(
            f"page1-layout: old-vertical-first-pixel x={old_left} y={old_y} "
            f"current-row0-first-x={columns[0].left}"
        )

    print(
        f"page1-layout: page=1 threshold={args.threshold} blanked_y=0..{PAGE1_IGNORE_ABOVE_Y - 1} "
        f"row0_top={row0_top}"
    )
    for column in columns:
        print(
            f"page1-layout: column={column.index + 1} left={column.left} right={column.right} "
            f"gutter={column.gutter_left}..{column.gutter_right}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
