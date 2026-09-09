from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class InferredStartGeometry:
    centers: tuple[int, ...]
    ranges: tuple[tuple[int, int], ...]
    observations: tuple[int, ...]


def _row_leftmosts(
    page_rows: Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    min_row_pixels: int = 3,
) -> list[int]:
    starts: list[int] = []
    for row in reference_rows:
        top = int(row["page_top"])
        bottom = int(row["page_bottom"])
        xs: list[int] = []
        for y in range(top, bottom):
            xs.extend(int(x) for x in page_rows.get(y, ()))
        if len(xs) >= min_row_pixels:
            starts.append(min(xs))
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
    page_rows: Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer legal row-start x regions from this page's own raster.

    There is deliberately no assumption that a page contains homonym starts,
    headword starts, continuation starts, or any fixed number of typographic
    start classes. We simply measure the physical leftmost row ink for every
    usable row on the current page, place a small x tolerance around each
    observed start, and merge overlapping intervals.

    Thus a page may naturally produce one, two, three, or more legal start
    regions. Even/odd pages and shifted columns are handled independently.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    observations = _row_leftmosts(page_rows, reference_rows)
    if not observations:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    ranges = _merge_start_intervals(observations, tolerance=tolerance)
    centers = tuple((lo + hi) // 2 for lo, hi in ranges)
    return InferredStartGeometry(
        centers=centers,
        ranges=ranges,
        observations=tuple(observations),
    )
