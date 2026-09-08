from __future__ import annotations

from dataclasses import dataclass


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
    """Classify whether a tiny upper row looks like a late overhanging fragment.

    This deliberately does *not* merge rows.  It provides geometric evidence
    for a later segmentation policy.  A low continuation row is protected when
    it has its own multi-row ink support near its own left edge.  Conversely a
    very small upper component that starts far to the right of the following
    row and lacks such support is flagged as a likely accent/overhang fragment.
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
