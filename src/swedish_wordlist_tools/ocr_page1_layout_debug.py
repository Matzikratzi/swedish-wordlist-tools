from __future__ import annotations

"""Detect page-1 text top and three column x-ranges from raw facsimile pixels.

This deliberately uses only the thresholded source PNG and absolute source
coordinates. For page 1 we hard-code that y < 60 and x=0..3 are irrelevant and
whiten them before any geometry is discovered. Coordinates are never renumbered.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast

fast = ultrafast.fast
PAGE1_IGNORE_ABOVE_Y = 60
PAGE1_IGNORE_THROUGH_X = 3
MIN_GUTTER_WIDTH = 3
MIN_COLUMN_PROBE_WIDTH = 20
MIN_BLOTCH_RUN_WIDTH = 30


@dataclass(frozen=True)
class ColumnRange:
    index: int
    left: int
    # Absolute x boundary immediately to the right of the column text area.
    right: int
    gutter_left: int
    gutter_right: int


@dataclass(frozen=True)
class BlotchRange:
    top: int
    left: int
    run_right: int
    bottom: int


@dataclass(frozen=True)
class Page1Layout:
    initial_top: int
    row0_tops: tuple[int, int, int]
    columns: list[ColumnRange]
    blotch: BlotchRange | None

    @property
    def row0_top(self) -> int:
        """Compatibility alias for the left column's row-0 top."""
        return self.row0_tops[0]


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
    pix = page.load()
    stop = max(0, min(int(y), page.height))
    for py in range(stop):
        for px in range(page.width):
            pix[px, py] = 255


def _blank_through_x(page: Image.Image, x: int) -> None:
    pix = page.load()
    stop = max(0, min(int(x) + 1, page.width))
    for px in range(stop):
        for py in range(page.height):
            pix[px, py] = 255


def _first_ink_row(page: Image.Image, start_y: int) -> int:
    pix = page.load()
    for y in range(max(0, start_y), page.height):
        for x in range(page.width):
            if pix[x, y] == 0:
                return y
    raise RuntimeError(f"no black pixel found at or below y={start_y}")


def _first_ink_row_in_range(page: Image.Image, start_y: int, left: int, right: int) -> int:
    """First absolute y with ink in half-open source x range [left,right)."""
    pix = page.load()
    x0 = max(0, left)
    x1 = min(page.width, right)
    for y in range(max(0, start_y), page.height):
        for x in range(x0, x1):
            if pix[x, y] == 0:
                return y
    raise RuntimeError(f"no black pixel found in x={x0}..{x1 - 1} at or below y={start_y}")


def _first_ink_x_on_row(page: Image.Image, y: int, start_x: int = 0) -> int | None:
    pix = page.load()
    if not (0 <= y < page.height):
        return None
    for x in range(max(0, start_x), page.width):
        if pix[x, y] == 0:
            return x
    return None


def _first_ink_y_in_column(page: Image.Image, x: int, start_y: int) -> int | None:
    pix = page.load()
    if not (0 <= x < page.width):
        return None
    for y in range(max(0, start_y), page.height):
        if pix[x, y] == 0:
            return y
    return None


def _vertical_occupancy(page: Image.Image, top: int) -> list[bool]:
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


def _find_black_run_on_row(
    page: Image.Image,
    y: int,
    left: int,
    right: int,
    *,
    min_width: int,
) -> tuple[int, int] | None:
    """Return first half-open black run [left,right) of at least min_width."""
    pix = page.load()
    x = max(0, left)
    stop = min(page.width, right)
    while x < stop:
        if pix[x, y] != 0:
            x += 1
            continue
        run_left = x
        while x < stop and pix[x, y] == 0:
            x += 1
        if x - run_left >= min_width:
            return run_left, x
    return None


def _detect_left_blotch(
    page: Image.Image,
    top: int,
    column: ColumnRange,
) -> BlotchRange | None:
    run = _find_black_run_on_row(
        page,
        top,
        column.left,
        column.right,
        min_width=MIN_BLOTCH_RUN_WIDTH,
    )
    if run is None:
        return None

    run_left, run_right = run
    pix = page.load()
    y = top
    while y < page.height and pix[run_left, y] == 0:
        y += 1
    return BlotchRange(top=top, left=run_left, run_right=run_right, bottom=y - 1)


def detect_page1_layout_details(page: Image.Image) -> Page1Layout:
    _blank_above(page, PAGE1_IGNORE_ABOVE_Y)
    _blank_through_x(page, PAGE1_IGNORE_THROUGH_X)
    initial_top = _first_ink_row(page, PAGE1_IGNORE_ABOVE_Y)
    occupied = _vertical_occupancy(page, initial_top)

    first_left = _first_ink_x_on_row(page, initial_top, PAGE1_IGNORE_THROUGH_X + 1)
    if first_left is None:
        raise RuntimeError(f"initial_top={initial_top} unexpectedly contains no black pixel")

    columns: list[ColumnRange] = []
    search_x = first_left
    for index in range(3):
        left = first_left if index == 0 else _next_black_column(occupied, search_x)
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
                ColumnRange(index=index, left=left, right=len(occupied), gutter_left=len(occupied), gutter_right=len(occupied))
            )
            break

        gutter_left, gutter_right = gutter
        columns.append(
            ColumnRange(
                index=index,
                left=left,
                right=gutter_left,
                gutter_left=gutter_left,
                gutter_right=gutter_right - 1,
            )
        )
        search_x = gutter_right

    if len(columns) != 3:
        raise RuntimeError(f"expected 3 columns, found {len(columns)}")

    natural_tops = tuple(
        _first_ink_row_in_range(page, PAGE1_IGNORE_ABOVE_Y, column.left, column.right)
        for column in columns
    )
    blotch = _detect_left_blotch(page, natural_tops[0], columns[0])
    if blotch is not None:
        # A blotch only tells us that the first ink at the top of this column is
        # not dictionary text. Once the blotch has ended, keep walking downward
        # inside the same absolute x range until actual ink re-enters. That first
        # black pixel row is row 0's roof.
        left_row0_top = _first_ink_row_in_range(
            page,
            blotch.bottom + 1,
            columns[0].left,
            columns[0].right,
        )
    else:
        left_row0_top = natural_tops[0]
    row0_tops = (left_row0_top, natural_tops[1], natural_tops[2])
    return Page1Layout(initial_top=initial_top, row0_tops=row0_tops, columns=columns, blotch=blotch)


def detect_page1_layout(page: Image.Image) -> tuple[int, list[ColumnRange]]:
    """Compatibility wrapper returning the left-column row top and columns."""
    layout = detect_page1_layout_details(page)
    return layout.row0_top, layout.columns


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect page-1 row=0 top and three columns from raw source pixels.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    if args.page != 1:
        raise ValueError("this detector is intentionally hard-coded for page 1")

    page = _load_thresholded_page(args.jsonl, args.page, args.threshold)
    layout = detect_page1_layout_details(page)

    occupied = _vertical_occupancy(page, layout.initial_top)
    old_left = _next_black_column(occupied, PAGE1_IGNORE_THROUGH_X + 1)
    if old_left is not None:
        old_y = _first_ink_y_in_column(page, old_left, layout.initial_top)
        print(
            f"page1-layout: old-vertical-first-pixel x={old_left} y={old_y} "
            f"current-initial-first-x={layout.columns[0].left}"
        )

    print(
        f"page1-layout: page=1 threshold={args.threshold} "
        f"blanked_y=0..{PAGE1_IGNORE_ABOVE_Y - 1} blanked_x=0..{PAGE1_IGNORE_THROUGH_X} "
        f"initial_top={layout.initial_top} row0_tops={','.join(str(y) for y in layout.row0_tops)}"
    )
    if layout.blotch is None:
        print(f"page1-layout: blotch=none min_black_run={MIN_BLOTCH_RUN_WIDTH}")
    else:
        b = layout.blotch
        print(
            f"page1-layout: blotch top={b.top} left={b.left} run_right={b.run_right} "
            f"run_width={b.run_right - b.left} bottom={b.bottom} left_row0_top={layout.row0_tops[0]}"
        )
    for column, row0_top in zip(layout.columns, layout.row0_tops):
        print(
            f"page1-layout: column={column.index + 1} left={column.left} right={column.right} "
            f"gutter={column.gutter_left}..{column.gutter_right} row0_top={row0_top}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
