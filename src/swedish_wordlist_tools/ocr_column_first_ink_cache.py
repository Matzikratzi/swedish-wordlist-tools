from __future__ import annotations

"""Cheap per-column cache of the leftmost black source pixel on every y row.

This is pure page geometry.  It does not classify glyphs or choose baselines.
For a fixed column interval [left, right), scan each pixel row once and remember
its first black x.  The same table also exposes the first/last y containing ink.

Absolute image column x=0 is ignored deliberately: some facsimiles contain a
spurious black edge there.  Other column-left pixels are kept unchanged.
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


def _cache(context: dict) -> dict[tuple[int, int], ColumnFirstInk]:
    return context.setdefault("raw_page_column_first_ink_cache", {})


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

    result = ColumnFirstInk(
        left=left,
        right=right,
        first_black_x=tuple(first_x),
        first_ink_y=first_y,
        last_ink_y=last_y,
        rows_with_ink=rows_with_ink,
    )
    _cache(context)[key] = result
    print(
        "raw-page-column-first-ink-cache: "
        f"left={left} right={right} first_y={first_y} last_y={last_y} "
        f"rows_with_ink={rows_with_ink}"
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
