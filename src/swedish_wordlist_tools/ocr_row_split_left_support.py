from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, TypeVar


@dataclass(frozen=True)
class RowLeftSupport:
    ink_pixels: int
    leftmost_x: int | None
    left_band_pixels: int
    left_band_rows: int


@dataclass(frozen=True)
class SplitLeftSupportDecision:
    upper: RowLeftSupport
    lower: RowLeftSupport
    start_delta: int | None
    upper_has_own_left_support: bool
    looks_like_late_upper_fragment: bool


@dataclass(frozen=True)
class RowStartGeometry:
    homonym_start_x: int
    headword_start_x: int
    continuation_start_x: int
    late_start_limit_x: int


T = TypeVar("T")


def row_start_geometry(
    homonym_start_x: int,
    headword_start_x: int,
    continuation_start_x: int,
) -> RowStartGeometry:
    """Build the typographic row-start gate from the three known start positions.

    A candidate may be slightly farther right than the continuation start, but
    not by more than half the headword->continuation indentation.  This is only
    a *gate*: a candidate inside it still needs real glyph/raster evidence.
    """
    if not homonym_start_x <= headword_start_x <= continuation_start_x:
        raise ValueError(
            "expected homonym_start_x <= headword_start_x <= continuation_start_x"
        )
    indent = continuation_start_x - headword_start_x
    if indent <= 0:
        raise ValueError("headword and continuation starts must be distinct")
    late_limit = continuation_start_x + ceil(indent / 2)
    return RowStartGeometry(
        homonym_start_x=homonym_start_x,
        headword_start_x=headword_start_x,
        continuation_start_x=continuation_start_x,
        late_start_limit_x=late_limit,
    )


def row_start_is_typographically_plausible(
    start_x: int,
    geometry: RowStartGeometry,
) -> bool:
    """Return whether x is still inside the region where a row may begin.

    This intentionally does not require x to equal one of the three canonical
    starts exactly.  Glyph antialiasing/raster shape can move the earliest black
    pixel a few pixels to the right; the hard rejection is only for a start that
    is more than half an indentation beyond the continuation start.
    """
    return start_x <= geometry.late_start_limit_x


def first_plausible_candidate_downward(
    candidates: Iterable[T],
    *,
    start_x,
    top_y,
    geometry: RowStartGeometry,
    previous_break_y: int,
    max_row_distance: int,
    strong_enough,
) -> T | None:
    """Pick the first strong candidate encountered while scanning downward.

    Candidates are ordered by their glyph top and then x.  A too-far-right hit
    never establishes a row, so scanning continues.  The search is bounded to
    one caller-supplied normal row distance from the preceding safe break.  The
    first strong candidate in the legal start zone wins; this is deliberately
    asymmetric so that a real low continuation row is not skipped in favour of
    a clearer headword row below it.
    """
    if max_row_distance < 0:
        raise ValueError("max_row_distance must be non-negative")
    limit_y = previous_break_y + max_row_distance
    ordered = sorted(candidates, key=lambda item: (top_y(item), start_x(item)))
    for candidate in ordered:
        y = top_y(candidate)
        if y < previous_break_y:
            continue
        if y > limit_y:
            break
        if not row_start_is_typographically_plausible(start_x(candidate), geometry):
            continue
        if not strong_enough(candidate):
            continue
        return candidate
    return None


def _support(
    black: set[tuple[int, int]],
    *,
    left_band_width: int,
    min_left_pixels: int,
    min_left_rows: int,
) -> tuple[RowLeftSupport, bool]:
    if not black:
        return RowLeftSupport(0, None, 0, 0), False
    leftmost = min(x for x, _y in black)
    band_right = leftmost + left_band_width
    left_band = {(x, y) for x, y in black if x < band_right}
    rows = {y for _x, y in left_band}
    support = RowLeftSupport(
        ink_pixels=len(black),
        leftmost_x=leftmost,
        left_band_pixels=len(left_band),
        left_band_rows=len(rows),
    )
    strong = len(left_band) >= min_left_pixels and len(rows) >= min_left_rows
    return support, strong


def split_left_support_decision(
    upper_black: set[tuple[int, int]],
    lower_black: set[tuple[int, int]],
    *,
    left_band_width: int = 12,
    max_start_delta: int = 16,
    min_left_pixels: int = 6,
    min_left_rows: int = 3,
    max_fragment_pixels: int = 24,
) -> SplitLeftSupportDecision:
    """Legacy geometric evidence for a suspicious upper fragment.

    Kept for the existing diagnostic.  ``upper_has_own_left_support`` is *not*
    sufficient proof of a real row (the apne accent disproves that).  New row
    start decisions should instead use ``row_start_geometry`` plus exact glyph
    evidence and ``first_plausible_candidate_downward``.
    """
    if left_band_width <= 0:
        raise ValueError("left_band_width must be positive")
    if max_start_delta < 0:
        raise ValueError("max_start_delta must be non-negative")

    upper, upper_strong = _support(
        upper_black,
        left_band_width=left_band_width,
        min_left_pixels=min_left_pixels,
        min_left_rows=min_left_rows,
    )
    lower, _lower_strong = _support(
        lower_black,
        left_band_width=left_band_width,
        min_left_pixels=min_left_pixels,
        min_left_rows=min_left_rows,
    )
    delta = None
    if upper.leftmost_x is not None and lower.leftmost_x is not None:
        delta = upper.leftmost_x - lower.leftmost_x

    late = (
        delta is not None
        and delta > max_start_delta
        and upper.ink_pixels <= max_fragment_pixels
        and not upper_strong
    )
    return SplitLeftSupportDecision(
        upper=upper,
        lower=lower,
        start_delta=delta,
        upper_has_own_left_support=upper_strong,
        looks_like_late_upper_fragment=late,
    )
