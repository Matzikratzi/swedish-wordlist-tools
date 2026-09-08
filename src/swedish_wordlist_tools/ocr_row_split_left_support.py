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


@dataclass(frozen=True)
class RowStartEvidence:
    x: int
    y: int


@dataclass(frozen=True)
class RowCompatibility:
    total_pixels: int
    explained_pixels: int
    unexplained_pixels: int
    outside_baseline_band: int

    @property
    def compatible(self) -> bool:
        return self.outside_baseline_band == 0


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
    """Return whether x is still inside the region where a row may begin."""
    return start_x <= geometry.late_start_limit_x


def first_typographic_start_evidence(
    black: set[tuple[int, int]],
    *,
    geometry: RowStartGeometry,
    previous_break_y: int,
    max_row_distance: int,
) -> RowStartEvidence | None:
    """Find the earliest raster row with ink at a legal row-start x.

    Crucially this does not require that the ink can already be named by the
    glyph facit.  An unknown first glyph is still evidence that a physical row
    may begin here.  Exact known glyphs are used later only to recover a
    baseline and explain as much of the row as possible.
    """
    if max_row_distance < 0:
        raise ValueError("max_row_distance must be non-negative")
    limit_y = previous_break_y + max_row_distance
    by_y: dict[int, int] = {}
    for x, y in black:
        if y < previous_break_y or y > limit_y:
            continue
        old = by_y.get(y)
        if old is None or x < old:
            by_y[y] = x
    for y in sorted(by_y):
        x = by_y[y]
        if row_start_is_typographically_plausible(x, geometry):
            return RowStartEvidence(x=x, y=y)
    return None


def baseline_row_compatibility(
    black: set[tuple[int, int]],
    covered: set[tuple[int, int]],
    *,
    baseline: int,
    min_relative_y: int,
    max_relative_y: int,
    vertical_slack: int = 0,
) -> RowCompatibility:
    """Judge whether unknown/unmatched ink can still belong to one baseline.

    Full facit coverage is deliberately *not* required: unknown glyphs may occur
    anywhere in a row.  Unexplained pixels are acceptable when they remain in
    the vertical band that the font's known glyph models occupy around the
    candidate baseline.  Ink outside that band is evidence that this baseline
    may be swallowing another physical row and must not be silently accepted.
    """
    if min_relative_y > max_relative_y:
        raise ValueError("min_relative_y must be <= max_relative_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    unexplained = black - covered
    lo = baseline + min_relative_y - vertical_slack
    hi = baseline + max_relative_y + vertical_slack
    outside = sum(1 for _x, y in unexplained if y < lo or y > hi)
    return RowCompatibility(
        total_pixels=len(black),
        explained_pixels=len(black & covered),
        unexplained_pixels=len(unexplained),
        outside_baseline_band=outside,
    )


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
    """Legacy helper: pick first strong known candidate at a legal x.

    New code must not assume the first glyph is known.  Prefer
    ``first_typographic_start_evidence`` to establish that a row starts in the
    legal zone, then use any known glyph on that same row to recover baseline.
    This helper remains for the existing diagnostics/tests.
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
    """Legacy geometric evidence for a suspicious upper fragment."""
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
