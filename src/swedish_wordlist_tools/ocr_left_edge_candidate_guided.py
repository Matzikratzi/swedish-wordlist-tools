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


def candidate_guided_exact_hits(
    black: set[tuple[int, int]],
    models: Iterable[GlyphModel],
    *,
    max_row_gap: int = 1,
    max_x: int | None = None,
    min_exact_steps: int = 1,
) -> tuple[tuple[GuidedExactHit, ...], GuidedStats]:
    """Walk source contours only as far as surviving glyph candidates require.

    For each possible horizontal resynchronisation x, the first source relation
    is looked up in the one-step local contour index.  Those concrete
    ``(glyph, model-offset)`` candidates are then extended one relation at a
    time.  A track dies immediately when the next ``(dy, dx)`` differs.

    The walk does not use a fixed maximum fingerprint length.  It continues
    only while at least one candidate survives and only down to the deepest
    occupied model row required by those candidates.  Whenever a surviving
    candidate already implies a full exact glyph placement, that placement is
    recorded; later matching relations may strengthen the same placement.
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
    max_requested_bottom_y: int | None = None

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
            started_tracks += 1

            # Each entry keeps the model-local occupied-row index that
            # corresponds to the source anchor, together with the indexed
            # one-step object used for exact placement verification.
            live: list[tuple[object, int]] = []
            for indexed in indexed_candidates:
                idx = anchor_index.get((id(indexed.model), indexed.anchor_y, indexed.anchor_x))
                if idx is not None:
                    live.append((indexed, idx))

            source_pos = start + 1
            matched_steps = 1
            while live:
                relation_steps += 1
                requested_bottom = max(
                    sy0 + (rows_by_model[id(indexed.model)][-1][0] - indexed.anchor_y)
                    for indexed, _idx in live
                )
                if max_requested_bottom_y is None or requested_bottom > max_requested_bottom_y:
                    max_requested_bottom_y = requested_bottom

                if matched_steps >= min_exact_steps:
                    for indexed, _idx in live:
                        exact_checks += 1
                        if not exact_local_model_at(
                            black,
                            indexed,
                            source_anchor_y=sy0,
                            source_anchor_x=sx0,
                        ):
                            continue
                        tx = sx0 - indexed.anchor_x
                        ty = sy0 - indexed.anchor_y
                        key = (id(indexed.model), tx, ty)
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
                        old = best.get(key)
                        if old is None or hit.matched_steps > old.matched_steps:
                            best[key] = hit

                next_source_pos = source_pos + 1
                if next_source_pos >= len(source_rows):
                    break
                sy_prev, sx_prev = source_rows[source_pos]
                sy_next, sx_next = source_rows[next_source_pos]
                if sy_next > requested_bottom:
                    break
                source_dy = sy_next - sy_prev
                if source_dy > max_row_gap:
                    break
                source_relation = (source_dy, sx_next - sx_prev)

                next_live: list[tuple[object, int]] = []
                for indexed, idx in live:
                    rows = rows_by_model[id(indexed.model)]
                    model_next = idx + matched_steps + 1
                    model_prev = model_next - 1
                    if model_next >= len(rows):
                        continue
                    my0, mx0 = rows[model_prev]
                    my1, mx1 = rows[model_next]
                    model_relation = (my1 - my0, mx1 - mx0)
                    if model_relation == source_relation:
                        next_live.append((indexed, idx))

                if not next_live:
                    break
                live = next_live
                source_pos = next_source_pos
                matched_steps += 1

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
    )
