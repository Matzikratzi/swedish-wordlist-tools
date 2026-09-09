from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_baseline_up import BaselineMatch, Pixel


@dataclass(frozen=True)
class LiveCandidateCheck:
    candidate: BaselineMatch
    alive: bool
    front_rows: int
    hidden_rows: int
    gap_rows: int
    contradiction_y: int | None = None


def _model_rows(candidate: BaselineMatch) -> dict[int, tuple[int, ...]]:
    rows: dict[int, list[int]] = {}
    for x, y in candidate.model.pixels:
        rows.setdefault(y, []).append(x)
    return {y: tuple(sorted(xs)) for y, xs in rows.items()}


def _candidate_span(candidate: BaselineMatch) -> tuple[int, int]:
    xs = [x for x, _y in candidate.pixels]
    return min(xs), max(xs)


def check_live_candidate(
    candidate: BaselineMatch,
    remaining_by_y: Mapping[int, Iterable[int]],
    *,
    after_left: int,
    column_right: int,
) -> LiveCandidateCheck:
    """Verify one placed glyph against the dynamic residual left profile.

    The candidate already has an absolute placement.  We now walk every raster
    row in its own vertical extent and apply the left-dominance rules:

    * expected glyph pixels must exist;
    * residual front == expected left edge => ``front``;
    * residual front farther left => candidate is temporarily ``hidden``;
    * residual front farther right, or no residual row, contradicts expected ink;
    * an internal horizontal gap must be blank inside the candidate's own x span.

    Ink farther right is irrelevant, and ink farther left is allowed because it
    can belong to another overlapping glyph.
    """
    rows = _model_rows(candidate)
    rel_top = candidate.model.min_y
    rel_bottom = candidate.model.max_y
    span_left, span_right = _candidate_span(candidate)
    occupied_rel_y = set(rows)
    internal_gaps = {
        rel_y
        for rel_y in range(rel_top + 1, rel_bottom)
        if rel_y not in occupied_rel_y
    }

    front_rows = 0
    hidden_rows = 0
    gap_rows = 0

    for rel_y in range(rel_top, rel_bottom + 1):
        page_y = candidate.baseline + rel_y
        residual_xs = tuple(
            sorted(
                x
                for x in remaining_by_y.get(page_y, ())
                if after_left < x < column_right
            )
        )
        model_xs = rows.get(rel_y)

        if model_xs is None:
            if rel_y in internal_gaps:
                if any(span_left <= x <= span_right for x in residual_xs):
                    return LiveCandidateCheck(
                        candidate=candidate,
                        alive=False,
                        front_rows=front_rows,
                        hidden_rows=hidden_rows,
                        gap_rows=gap_rows,
                        contradiction_y=page_y,
                    )
                gap_rows += 1
            continue

        expected_xs = tuple(candidate.tx + x for x in model_xs)
        residual_set = set(residual_xs)
        if not set(expected_xs).issubset(residual_set):
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=page_y,
            )

        if not residual_xs:
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=page_y,
            )

        expected_left = min(expected_xs)
        observed_left = residual_xs[0]
        if observed_left > expected_left:
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=page_y,
            )
        if observed_left == expected_left:
            front_rows += 1
        else:
            hidden_rows += 1

    return LiveCandidateCheck(
        candidate=candidate,
        alive=True,
        front_rows=front_rows,
        hidden_rows=hidden_rows,
        gap_rows=gap_rows,
    )


def live_survivors(
    candidates: Iterable[BaselineMatch],
    remaining_by_y: Mapping[int, Iterable[int]],
    *,
    after_left: int,
    column_right: int,
) -> tuple[LiveCandidateCheck, ...]:
    checks = [
        check_live_candidate(
            candidate,
            remaining_by_y,
            after_left=after_left,
            column_right=column_right,
        )
        for candidate in candidates
    ]
    return tuple(
        sorted(
            (check for check in checks if check.alive),
            key=lambda check: (
                check.candidate.left,
                -check.front_rows,
                check.hidden_rows,
                -len(check.candidate.pixels),
                -check.candidate.model.sources,
                check.candidate.model.label,
                check.candidate.model.style,
            ),
        )
    )


def _front_signature(check: LiveCandidateCheck) -> frozenset[int]:
    """Raster rows on which this candidate itself owns the residual front."""
    candidate = check.candidate
    rows = _model_rows(candidate)
    owned: set[int] = set()
    for rel_y, model_xs in rows.items():
        page_y = candidate.baseline + rel_y
        expected_left = candidate.tx + min(model_xs)
        # check_live_candidate has already established that the candidate is
        # alive.  Reconstructing ownership from its counters is impossible, so
        # callers that need dominance use this helper only through the explicit
        # residual map in _front_dominant_semantics below.
        owned.add(page_y if expected_left >= candidate.left else page_y)
    return frozenset(owned)


def _front_dominant_semantics(
    checks: tuple[LiveCandidateCheck, ...],
) -> tuple[LiveCandidateCheck, ...]:
    """Keep a unique interpretation only when it has strictly more front evidence.

    This is deliberately conservative: a larger glyph is not preferred merely
    because it contains more pixels.  It must own the residual left edge on more
    raster rows than every competing semantic interpretation.  A tie remains
    unresolved and will require sequence lookahead.
    """
    if len(checks) < 2:
        return checks
    best_front = max(check.front_rows for check in checks)
    best = tuple(check for check in checks if check.front_rows == best_front)
    if len(best) != 1:
        return checks
    runner_up = max(
        (check.front_rows for check in checks if check is not best[0]),
        default=-1,
    )
    if best_front <= runner_up:
        return checks
    return best


def pick_unique_live_semantic(
    candidates: Iterable[BaselineMatch],
    remaining_by_y: Mapping[int, Iterable[int]],
    *,
    after_left: int,
    column_right: int,
) -> tuple[BaselineMatch | None, tuple[LiveCandidateCheck, ...]]:
    """Return a glyph only when one leftmost semantic interpretation survives.

    Raster variants with the same label/style/translation/baseline are one
    semantic interpretation.  If several different glyph interpretations are
    still live, first ask whether exactly one of them owns strictly more rows of
    the residual left edge.  This is stronger evidence than pixel count: it is
    the whole-column profile itself.  Equal front evidence remains unresolved
    for sequence lookahead.
    """
    survivors = live_survivors(
        candidates,
        remaining_by_y,
        after_left=after_left,
        column_right=column_right,
    )
    if not survivors:
        return None, survivors

    left = min(check.candidate.left for check in survivors)
    left_group = tuple(check for check in survivors if check.candidate.left == left)

    semantics: dict[tuple[str, str, int, int], list[LiveCandidateCheck]] = {}
    for check in left_group:
        hit = check.candidate
        semantics.setdefault(
            (hit.model.label, hit.model.style, hit.tx, hit.baseline),
            [],
        ).append(check)

    if len(semantics) != 1:
        representatives = tuple(
            max(
                checks,
                key=lambda check: (
                    check.front_rows,
                    len(check.candidate.pixels),
                    check.candidate.model.sources,
                    -check.hidden_rows,
                ),
            )
            for checks in semantics.values()
        )
        dominant = _front_dominant_semantics(representatives)
        if len(dominant) != 1:
            return None, left_group
        return dominant[0].candidate, left_group

    only = next(iter(semantics.values()))
    best = max(
        only,
        key=lambda check: (
            check.front_rows,
            len(check.candidate.pixels),
            check.candidate.model.sources,
            -check.hidden_rows,
        ),
    )
    return best.candidate, left_group
