from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile


@dataclass(frozen=True)
class InferredStartGeometry:
    centers: tuple[int, ...]
    ranges: tuple[tuple[int, int], ...]
    observations: tuple[int, ...]


def _row_leftmosts(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    min_row_pixels: int = 3,
) -> list[int]:
    reference = list(reference_rows)
    if isinstance(source, ColumnLeftProfile):
        profile = source
    else:
        if not reference:
            return []
        top = min(int(row["page_top"]) for row in reference)
        bottom = max(int(row["page_bottom"]) for row in reference)
        profile = build_column_left_profile(source, top=top, bottom=bottom)

    starts: list[int] = []
    for row in reference:
        top = int(row["page_top"])
        bottom = int(row["page_bottom"])
        x = profile.row_leftmost(top, bottom)
        if x is None:
            continue

        # Preserve the old tiny-noise guard for mapping callers.  A prebuilt
        # page profile has already been constructed from the column bitmap, so
        # there is no need to walk every x merely to rediscover its minimum.
        if not isinstance(source, ColumnLeftProfile):
            count = sum(len(tuple(source.get(y, ()))) for y in range(top, bottom))
            if count < min_row_pixels:
                continue
        starts.append(x)
    return starts


def _merge_start_intervals(values: Iterable[int], *, tolerance: int) -> tuple[tuple[int, int], ...]:
    intervals = sorted((int(x) - tolerance, int(x) + tolerance) for x in values)
    if not intervals:
        return ()

    merged: list[list[int]] = []
    for lo, hi in intervals:
        if not merged or lo > merged[-1][1] + 1:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return tuple((lo, hi) for lo, hi in merged)


def infer_page_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer legal row-start x regions from this page's own raster/profile.

    There is deliberately no assumption that a page contains homonym starts,
    headword starts, continuation starts, or any fixed number of typographic
    start classes.  When a whole-column profile is supplied, each row start is
    just the minimum profile x over that row span; no per-row collection of all
    black x coordinates is needed.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    observations = _row_leftmosts(source, reference_rows)
    if not observations:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    ranges = _merge_start_intervals(observations, tolerance=tolerance)
    centers = tuple((lo + hi) // 2 for lo, hi in ranges)
    return InferredStartGeometry(
        centers=centers,
        ranges=ranges,
        observations=tuple(observations),
    )
