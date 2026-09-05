from __future__ import annotations

"""Cheap per-column cache of the leftmost black source pixel on every y row.

This is pure page geometry. It does not classify glyphs or choose baselines.
For a fixed column interval [left, right), scan each pixel row once and remember
its first black x. The same table also exposes the first/last y containing ink
and contiguous all-white y intervals inside the column.

Absolute image column x=0 is ignored deliberately: some facsimiles contain a
spurious black edge there. Other column-left pixels are kept unchanged.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnFirstInk:
    left: int
    right: int
    first_black_x: tuple[int, ...]
    first_ink_y: int | None
    last_ink_y: int | None
    rows_with_ink: int
    white_gaps: tuple[tuple[int, int], ...]


def _cache(context: dict) -> dict[tuple[int, int], ColumnFirstInk]:
    return context.setdefault("raw_page_column_first_ink_cache", {})


def _white_gaps(first_x: list[int]) -> tuple[tuple[int, int], ...]:
    """Return half-open [y0,y1) runs whose complete column row is white."""
    gaps: list[tuple[int, int]] = []
    start: int | None = None
    for y, x in enumerate(first_x):
        if x < 0:
            if start is None:
                start = y
        elif start is not None:
            gaps.append((start, y))
            start = None
    if start is not None:
        gaps.append((start, len(first_x)))
    return tuple(gaps)


def get_column_first_ink(context: dict, *, left: int, right: int) -> ColumnFirstInk:
    owners = context["pixel_owners"]
    left = max(0, int(left))
    right = min(owners.width, int(right))
    key = (left, right)
    cached = _cache(context).get(key)
    if cached is not None:
        return cached

    scan_left = max(left, 1)  # ignore the known bad absolute image column x=0
    data = owners.data
    width = owners.width
    first_x = [-1] * owners.height
    first_y: int | None = None
    last_y: int | None = None
    rows_with_ink = 0

    if scan_left < right:
        for y in range(owners.height):
            base = y * width
            found = -1
            for x in range(scan_left, right):
                if data[base + x] != 0:
                    found = x
                    break
            first_x[y] = found
            if found >= 0:
                rows_with_ink += 1
                if first_y is None:
                    first_y = y
                last_y = y

    gaps = _white_gaps(first_x)
    result = ColumnFirstInk(
        left=left,
        right=right,
        first_black_x=tuple(first_x),
        first_ink_y=first_y,
        last_ink_y=last_y,
        rows_with_ink=rows_with_ink,
        white_gaps=gaps,
    )
    _cache(context)[key] = result

    internal = [
        (y0, y1)
        for y0, y1 in gaps
        if first_y is not None
        and last_y is not None
        and y0 > first_y
        and y1 - 1 < last_y
    ]
    longest = sorted(internal, key=lambda gap: (gap[1] - gap[0], -gap[0]), reverse=True)[:8]
    gap_summary = ",".join(
        f"{y0}-{y1 - 1}({y1 - y0})" for y0, y1 in longest
    ) or "none"
    print(
        "raw-page-column-first-ink-cache: "
        f"left={left} right={right} first_y={first_y} last_y={last_y} "
        f"rows_with_ink={rows_with_ink} white_gaps={len(internal)} "
        f"longest_white_gaps={gap_summary}"
    )
    return result


def first_start_band_ink_y(
    context: dict,
    *,
    search_from: int,
    search_to: int,
    left: int,
    right: int,
    start_band_right: int,
) -> int | None:
    """Return first y whose cached leftmost ink lies in the allowed start band."""
    cached = get_column_first_ink(context, left=left, right=right)
    y0 = max(0, int(search_from))
    y1 = min(len(cached.first_black_x), int(search_to))
    x1 = min(int(right), int(start_band_right))
    for y in range(y0, y1):
        x = cached.first_black_x[y]
        if int(left) <= x < x1:
            return y
    return None


def install_on_scanner(scanner) -> None:
    """Make the scanner's initial-border lookup use this cache.

    Keep the scanner function signature unchanged so this is a transparent
    optimization: callers still ask for first ink in a start band, but the
    answer comes from one cached x value per pixel row.
    """

    def _cached_first_ink_y(
        context: dict,
        *,
        search_from: int,
        search_to: int,
        left: int,
        right: int,
    ) -> int | None:
        _x0, x1 = scanner._start_band(left, right)
        return first_start_band_ink_y(
            context,
            search_from=search_from,
            search_to=search_to,
            left=left,
            right=right,
            start_band_right=x1,
        )

    scanner._first_ink_y = _cached_first_ink_y
