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


@dataclass(frozen=True)
class ConservativeSplitRepair:
    repair: bool
    reason: str


T = TypeVar("T")


def row_start_geometry(
    homonym_start_x: int,
    headword_start_x: int,
    continuation_start_x: int,
) -> RowStartGeometry:
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
    return start_x <= geometry.late_start_limit_x


def first_typographic_start_evidence(
    black: set[tuple[int, int]],
    *,
    geometry: RowStartGeometry,
    previous_break_y: int,
    max_row_distance: int,
) -> RowStartEvidence | None:
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


def conservative_split_repair_decision(
    upper_black: set[tuple[int, int]],
    combined_black: set[tuple[int, int]],
    *,
    geometry: RowStartGeometry,
    establishing_start_x: int | None,
    compatibility: RowCompatibility | None,
    max_upper_pixels: int = 24,
) -> ConservativeSplitRepair:
    """Conservatively suppress a pseudo-row above an established real row.

    This deliberately repairs only a narrow case: the old upper row is tiny,
    starts too far right to be a typographic row start, a known glyph has
    established the following row in the legal start region, and all ink in the
    combined region is compatible with that baseline.  Otherwise the old split
    is retained unchanged.
    """
    if not upper_black:
        return ConservativeSplitRepair(False, "empty-upper")
    if len(upper_black) > max_upper_pixels:
        return ConservativeSplitRepair(False, "upper-not-tiny")
    upper_left = min(x for x, _y in upper_black)
    if row_start_is_typographically_plausible(upper_left, geometry):
        return ConservativeSplitRepair(False, "upper-could-start-row")
    if establishing_start_x is None:
        return ConservativeSplitRepair(False, "no-established-row")
    if not row_start_is_typographically_plausible(establishing_start_x, geometry):
        return ConservativeSplitRepair(False, "established-start-not-legal")
    if compatibility is None or not compatibility.compatible:
        return ConservativeSplitRepair(False, "combined-ink-not-baseline-compatible")
    if not combined_black:
        return ConservativeSplitRepair(False, "empty-combined")
    return ConservativeSplitRepair(True, "tiny-late-upper-belongs-to-established-row")


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
