from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from typing import Iterable

from .ocr_left_edge_local_index import (
    LocalExactHit,
    PreparedLocalFingerprintIndexes,
    TranslateXRange,
    exact_local_model_at,
)


def _sorted_source_rows(black: set[tuple[int, int]]) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Store source x positions once per raster row for cheap thresholded contours."""
    by_y: dict[int, list[int]] = defaultdict(list)
    for x, y in black:
        by_y[y].append(x)
    return tuple((y, tuple(sorted(xs))) for y, xs in sorted(by_y.items()))


def _thresholded_source_signatures(
    rows: tuple[tuple[int, tuple[int, ...]], ...],
    *,
    threshold_x: int,
    steps: int,
    max_row_gap: int,
) -> tuple[tuple[int, int, tuple[tuple[int, int], ...]], ...]:
    """Equivalent to source_local_signatures(min_x=threshold_x) without rescanning pixels."""
    contour: list[tuple[int, int]] = []
    for y, xs in rows:
        index = bisect_left(xs, threshold_x)
        if index < len(xs):
            contour.append((y, xs[index]))
    if len(contour) < steps + 1:
        return ()

    out: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
    for start in range(len(contour) - steps):
        window = contour[start : start + steps + 1]
        signature: list[tuple[int, int]] = []
        valid = True
        for (y0, x0), (y1, x1) in zip(window, window[1:]):
            dy = y1 - y0
            if dy > max_row_gap:
                valid = False
                break
            signature.append((dy, x1 - x0))
        if valid:
            out.append((window[0][0], window[0][1], tuple(signature)))
    return tuple(out)


def ranked_exact_row_start_band_hits(
    black: set[tuple[int, int]],
    *,
    prepared: PreparedLocalFingerprintIndexes,
    start_ranges: Iterable[TranslateXRange],
    min_steps: int = 3,
    max_steps: int = 8,
    max_row_gap: int = 1,
    observation_right_slack: int = 12,
) -> tuple[LocalExactHit, ...]:
    """Find exact row-start glyph placements with reusable thresholded contours.

    Every integer x inside the typographically legal row-start bands is still a
    contour resynchronisation threshold, preserving the completeness of the old
    dense search.  Unlike that search, source pixels are grouped and sorted by y
    once; each threshold then selects its first x with binary search instead of
    rescanning the whole column.  The derived glyph origin must lie inside a real
    start band and the complete glyph raster is verified exactly against black.

    ``observation_right_slack`` remains accepted for CLI/API compatibility with
    the previous one-contour experiment; the thresholded contour no longer needs
    an artificial right edge.
    """
    if min_steps <= 0 or max_steps < min_steps:
        raise ValueError("invalid step range")
    if observation_right_slack < 0:
        raise ValueError("observation_right_slack must be non-negative")
    if (prepared.min_steps, prepared.max_steps, prepared.max_row_gap) != (
        min_steps,
        max_steps,
        max_row_gap,
    ):
        raise ValueError("prepared fingerprint parameters do not match search parameters")

    ranges = tuple((int(lo), int(hi)) for lo, hi in start_ranges)
    if not ranges or any(lo > hi for lo, hi in ranges):
        raise ValueError("start_ranges must contain valid ranges")

    thresholds = tuple(sorted({x for lo, hi in ranges for x in range(lo, hi + 1)}))
    source_rows = _sorted_source_rows(black)
    signatures_by_steps_and_threshold = {
        (steps, threshold_x): _thresholded_source_signatures(
            source_rows,
            threshold_x=threshold_x,
            steps=steps,
            max_row_gap=max_row_gap,
        )
        for steps in range(max_steps, min_steps - 1, -1)
        for threshold_x in thresholds
    }

    hits: list[LocalExactHit] = []
    seen: set[tuple[int, int, int]] = set()
    for steps in range(max_steps, min_steps - 1, -1):
        index = prepared.indexes[steps]
        for threshold_x in thresholds:
            for source_y, source_x, signature in signatures_by_steps_and_threshold[(steps, threshold_x)]:
                for indexed in index.candidates(signature):
                    tx = source_x - indexed.anchor_x
                    if not any(start_lo <= tx <= start_hi for start_lo, start_hi in ranges):
                        continue
                    ty = source_y - indexed.anchor_y
                    placement_key = (id(indexed.model), tx, ty)
                    if placement_key in seen:
                        continue
                    if not exact_local_model_at(
                        black,
                        indexed,
                        source_anchor_y=source_y,
                        source_anchor_x=source_x,
                    ):
                        continue
                    seen.add(placement_key)
                    hits.append(LocalExactHit(indexed, source_y, source_x, steps, threshold_x))

    hits.sort(
        key=lambda hit: (
            -hit.steps,
            -len(hit.model.pixels),
            hit.translate_x,
            hit.translate_y,
            hit.model.label,
            hit.model.style,
            hit.indexed.anchor_y,
        )
    )
    return tuple(hits)
