from __future__ import annotations

from typing import Iterable

from .ocr_left_edge_local_index import (
    LocalExactHit,
    PreparedLocalFingerprintIndexes,
    TranslateXRange,
    exact_local_model_at,
    source_local_signatures,
)


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
    """Find exact glyph placements using one source contour per start band.

    Row-start typography gives us a few narrow x bands where a glyph origin may
    legitimately occur.  Build the source left contour once per band and step
    count instead of rebuilding it for every possible x threshold.  The source
    observation extends slightly to the right so a glyph starting near the
    band's right edge can still contribute its full left contour.  Acceptance is
    nevertheless gated by the derived full-glyph translate_x inside a real start
    band, and the complete glyph raster is verified against ``black``.
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

    hits: list[LocalExactHit] = []
    seen: set[tuple[int, int, int]] = set()
    for lo, hi in ranges:
        observation = {
            (x, y)
            for x, y in black
            if lo <= x <= hi + observation_right_slack
        }
        for steps in range(max_steps, min_steps - 1, -1):
            index = prepared.indexes[steps]
            for source_y, source_x, signature in source_local_signatures(
                observation,
                steps=steps,
                max_row_gap=max_row_gap,
            ):
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
                    hits.append(LocalExactHit(indexed, source_y, source_x, steps, lo))

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
