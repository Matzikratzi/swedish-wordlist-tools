from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ColumnLeftProfile:
    """Whole-column leftmost-ink profile in absolute page coordinates.

    ``values[i]`` corresponds to absolute page y ``top + i`` and is the
    absolute x coordinate of the leftmost black pixel on that raster row, or
    ``None`` when the row is blank inside the column.
    """

    top: int
    bottom: int
    values: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if self.bottom < self.top:
            raise ValueError("bottom must be >= top")
        if len(self.values) != self.bottom - self.top:
            raise ValueError("profile length must equal bottom-top")

    def at(self, y: int) -> int | None:
        if y < self.top or y >= self.bottom:
            return None
        return self.values[y - self.top]

    def nonblank_y(self, start: int | None = None, stop: int | None = None) -> Iterable[int]:
        lo = self.top if start is None else max(self.top, int(start))
        hi = self.bottom if stop is None else min(self.bottom, int(stop))
        for y in range(lo, hi):
            if self.values[y - self.top] is not None:
                yield y

    def row_leftmost(self, top: int, bottom: int) -> int | None:
        lo = max(self.top, int(top))
        hi = min(self.bottom, int(bottom))
        if hi <= lo:
            return None
        xs = (
            self.values[y - self.top]
            for y in range(lo, hi)
            if self.values[y - self.top] is not None
        )
        return min(xs, default=None)

    def changes(self) -> tuple[tuple[int, int | None, int | None], ...]:
        """Return y events where the profile value changes.

        This deliberately records ``dx=0`` as no event by simply omitting
        unchanged rows. Blank<->ink transitions are events. The richer
        two-difference fingerprint idea is intentionally left for the next
        matching step; this method only exposes the raw page-wide events.
        """
        events: list[tuple[int, int | None, int | None]] = []
        previous: int | None = None
        have_previous = False
        for offset, current in enumerate(self.values):
            y = self.top + offset
            if not have_previous:
                previous = current
                have_previous = True
                continue
            if current != previous:
                events.append((y, previous, current))
            previous = current
        return tuple(events)


def build_column_left_profile(
    page_rows: Mapping[int, Iterable[int]],
    *,
    top: int,
    bottom: int,
    left: int | None = None,
    right: int | None = None,
) -> ColumnLeftProfile:
    """Build the whole-column profile once from an existing y->x row index."""
    top = int(top)
    bottom = int(bottom)
    if bottom < top:
        raise ValueError("bottom must be >= top")

    values: list[int | None] = []
    for y in range(top, bottom):
        row = page_rows.get(y, ())
        best: int | None = None
        for raw_x in row:
            x = int(raw_x)
            if left is not None and x < left:
                continue
            if right is not None and x > right:
                continue
            if best is None or x < best:
                best = x
        values.append(best)

    return ColumnLeftProfile(top=top, bottom=bottom, values=tuple(values))
