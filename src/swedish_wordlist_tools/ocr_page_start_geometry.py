from __future__ import annotations

from collections import Counter
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


def _smoothed_votes(values: Iterable[int], *, radius: int = 2) -> Counter[int]:
    raw = Counter(int(v) for v in values)
    if not raw:
        return Counter()
    lo = min(raw)
    hi = max(raw)
    out: Counter[int] = Counter()
    for x in range(lo, hi + 1):
        out[x] = sum(raw.get(xx, 0) for xx in range(x - radius, x + radius + 1))
    return out


def _pick_peaks(votes: Counter[int], *, count: int = 3, min_separation: int = 7) -> list[int]:
    peaks: list[int] = []
    for x, score in sorted(votes.items(), key=lambda item: (-item[1], item[0])):
        if score <= 0:
            break
        if any(abs(x - old) < min_separation for old in peaks):
            continue
        peaks.append(x)
        if len(peaks) >= count:
            break
    return sorted(peaks)


def infer_page_start_geometry(
    page_rows: Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 7,
    peak_radius: int = 2,
    min_peak_separation: int = 7,
) -> InferredStartGeometry:
    """Infer typographic row-start x bands from the current page itself.

    The input rows are used only as vertical sampling windows. Horizontal start
    positions are measured from the page raster, so even/odd pages and shifted
    columns get their own geometry rather than inheriting global x constants.

    We smooth the histogram of physical leftmost row ink and select up to three
    separated modes. The ranges are deliberately tolerant because the physical
    leftmost ink can differ a few pixels from the glyph translation x depending
    on the first glyph shape/overhang.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    observations = _row_leftmosts(page_rows, reference_rows)
    if not observations:
        return InferredStartGeometry(centers=(), ranges=(), observations=())
    votes = _smoothed_votes(observations, radius=peak_radius)
    centers = tuple(_pick_peaks(votes, count=3, min_separation=min_peak_separation))
    ranges = tuple((center - tolerance, center + tolerance) for center in centers)
    return InferredStartGeometry(
        centers=centers,
        ranges=ranges,
        observations=tuple(observations),
    )
