from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel
from .ocr_left_edge_local_index import LocalLeftEdgeIndex, exact_local_model_at, occupied_left_rows


@dataclass(frozen=True)
class GuidedExactHit:
    model: GlyphModel
    source_anchor_y: int
    source_anchor_x: int
    model_anchor_y: int
    model_anchor_x: int
    matched_steps: int
    scan_x: int
    requested_bottom_y: int

    @property
    def translate_x(self) -> int:
        return self.source_anchor_x - self.model_anchor_x

    @property
    def translate_y(self) -> int:
        return self.source_anchor_y - self.model_anchor_y

    @property
    def baseline(self) -> int:
        return self.translate_y


@dataclass(frozen=True)
class GuidedStats:
    scan_positions: int
    started_tracks: int
    relation_steps: int
    exact_checks: int
    max_requested_bottom_y: int | None
    expected_pixel_checks: int = 0


def _source_left_rows(
    black: set[tuple[int, int]],
    *,
    min_x: int,
) -> tuple[tuple[int, int], ...]:
    by_y: dict[int, int] = {}
    for x, y in black:
        if x < min_x:
            continue
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(sorted(by_y.items()))


def _extend_expected_contour(
    black: set[tuple[int, int]],
    rows: tuple[tuple[int, int], ...],
    *,
    anchor_index: int,
    source_anchor_y: int,
    source_anchor_x: int,
    max_row_gap: int,
) -> tuple[int, int, int]:
    """Follow one model candidate by probing only its expected contour pixels.

    The first relation has already matched.  That fixes the model translation.
    Every subsequent model contour row therefore predicts one exact source
    ``(x, y)`` position.  We test only those positions instead of rebuilding a
    source contour and comparing it wholesale.

    Returns ``(matched_steps, requested_bottom_y, pixel_checks)``.  A model-side
    white-row gap larger than ``max_row_gap`` ends this local fingerprint run;
    there is deliberately no invented dx relation across the gap.
    """
    tx = source_anchor_x - rows[anchor_index][1]
    ty = source_anchor_y - rows[anchor_index][0]

    # Candidate creation guarantees that relation anchor_index -> anchor_index+1
    # matched, so one real relation is already known.
    matched_steps = 1
    requested_bottom_y = source_anchor_y + (rows[anchor_index + 1][0] - rows[anchor_index][0])
    pixel_checks = 0

    prev_index = anchor_index + 1
    next_index = prev_index + 1
    while next_index < len(rows):
        py, _px = rows[prev_index]
        ny, nx = rows[next_index]
        dy = ny - py
        if dy > max_row_gap:
            break

        expected_y = ny + ty
        expected_x = nx + tx
        requested_bottom_y = expected_y
        pixel_checks += 1
        if (expected_x, expected_y) not in black:
            break

        matched_steps += 1
        prev_index = next_index
        next_index += 1

    return matched_steps, requested_bottom_y, pixel_checks


def candidate_guided_exact_hits(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    max_row_gap: int = 1,
    max_x: int | None = None,
    min_exact_steps: int = 1,
) -> tuple[tuple[GuidedExactHit, ...], GuidedStats]:
    """Find exact placements by letting each glyph candidate guide the walk.

    Candidate generation still uses one observed source ``(dy, dx)`` relation.
    That one relation identifies concrete ``(glyph, model-offset)`` candidates
    and fixes each candidate's translation.  From then on the source contour is
    *not* regenerated.  Instead, the candidate predicts the exact source pixel
    for its next occupied model row.  The walk continues while those predicted
    pixels exist, and stops at the model's end, a model-side white-row gap, or
    the first missing predicted pixel.

    Full glyph raster verification is done once per sufficiently long track,
    after the cheap guided contour walk.  Thus a candidate can ask us to look
    farther down than an arbitrary fixed 8-step fingerprint without paying for
    repeated full-raster checks at every intermediate step.
    """
    if max_row_gap <= 0:
        raise ValueError("max_row_gap must be positive")
    if min_exact_steps <= 0:
        raise ValueError("min_exact_steps must be positive")

    model_rows = tuple(models)
    one_step = LocalLeftEdgeIndex(model_rows, steps=1, max_row_gap=max_row_gap)
    rows_by_model = {id(model): occupied_left_rows(model) for model in model_rows}
    anchor_index: dict[tuple[int, int, int], int] = {}
    for model in model_rows:
        rows = rows_by_model[id(model)]
        for i, (y, x) in enumerate(rows):
            anchor_index[(id(model), y, x)] = i

    scan_xs = sorted({x for x, _y in black if max_x is None or x <= max_x})
    best: dict[tuple[int, int, int], GuidedExactHit] = {}
    started_tracks = 0
    relation_steps = 0
    exact_checks = 0
    expected_pixel_checks = 0
    max_requested_bottom_y: int | None = None

    # The same concrete candidate placement can be rediscovered from several
    # scan_x values / source windows.  Extend and exact-check it only once for a
    # given model-local anchor; retain the strongest resulting placement below.
    seen_tracks: set[tuple[int, int, int, int]] = set()

    for scan_x in scan_xs:
        source_rows = _source_left_rows(black, min_x=scan_x)
        if len(source_rows) < 2:
            continue

        for start in range(len(source_rows) - 1):
            (sy0, sx0), (sy1, sx1) = source_rows[start], source_rows[start + 1]
            first_dy = sy1 - sy0
            if first_dy > max_row_gap:
                continue
            signature = ((first_dy, sx1 - sx0),)
            indexed_candidates = one_step.candidates(signature)
            if not indexed_candidates:
                continue

            for indexed in indexed_candidates:
                idx = anchor_index.get((id(indexed.model), indexed.anchor_y, indexed.anchor_x))
                if idx is None:
                    continue
                rows = rows_by_model[id(indexed.model)]
                if idx + 1 >= len(rows):
                    continue

                tx = sx0 - indexed.anchor_x
                ty = sy0 - indexed.anchor_y
                track_key = (id(indexed.model), idx, tx, ty)
                if track_key in seen_tracks:
                    continue
                seen_tracks.add(track_key)
                started_tracks += 1

                matched_steps, requested_bottom, checks = _extend_expected_contour(
                    black,
                    rows,
                    anchor_index=idx,
                    source_anchor_y=sy0,
                    source_anchor_x=sx0,
                    max_row_gap=max_row_gap,
                )
                relation_steps += matched_steps
                expected_pixel_checks += checks
                if max_requested_bottom_y is None or requested_bottom > max_requested_bottom_y:
                    max_requested_bottom_y = requested_bottom

                if matched_steps < min_exact_steps:
                    continue

                exact_checks += 1
                if not exact_local_model_at(
                    black,
                    indexed,
                    source_anchor_y=sy0,
                    source_anchor_x=sx0,
                ):
                    continue

                placement_key = (id(indexed.model), tx, ty)
                hit = GuidedExactHit(
                    model=indexed.model,
                    source_anchor_y=sy0,
                    source_anchor_x=sx0,
                    model_anchor_y=indexed.anchor_y,
                    model_anchor_x=indexed.anchor_x,
                    matched_steps=matched_steps,
                    scan_x=scan_x,
                    requested_bottom_y=requested_bottom,
                )
                old = best.get(placement_key)
                if old is None or hit.matched_steps > old.matched_steps:
                    best[placement_key] = hit

    hits = sorted(
        best.values(),
        key=lambda hit: (
            -hit.matched_steps,
            -len(hit.model.pixels),
            hit.translate_x,
            hit.translate_y,
            hit.model.label,
            hit.model.style,
        ),
    )
    return tuple(hits), GuidedStats(
        scan_positions=len(scan_xs),
        started_tracks=started_tracks,
        relation_steps=relation_steps,
        exact_checks=exact_checks,
        max_requested_bottom_y=max_requested_bottom_y,
        expected_pixel_checks=expected_pixel_checks,
    )
