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


def _residual_row(
    remaining_by_y: Mapping[int, Iterable[int]],
    page_y: int,
    *,
    after_left: int,
    column_right: int,
) -> tuple[int, ...]:
    return tuple(
        sorted(
            x
            for x in remaining_by_y.get(page_y, ())
            if after_left < x < column_right
        )
    )


def _terminal_event_holds(
    remaining_by_y: Mapping[int, Iterable[int]],
    page_ys: Iterable[int],
    *,
    after_left: int,
    column_right: int,
    span_right: int,
) -> tuple[bool, int | None]:
    """Check the first next profile pixel across a known candidate edge.

    A glyph ending at ``span_right`` requires the next observed residual profile
    pixel to have moved strictly to the right of the glyph. Blank raster rows do
    not decide the event; they are skipped until the next profile pixel. If the
    already-known extent contains no next profile pixel, there is not enough
    evidence to reject the candidate.
    """
    for page_y in page_ys:
        residual_xs = _residual_row(
            remaining_by_y,
            page_y,
            after_left=after_left,
            column_right=column_right,
        )
        if not residual_xs:
            continue
        return residual_xs[0] > span_right, page_y
    return True, None


def check_live_candidate(
    candidate: BaselineMatch,
    remaining_by_y: Mapping[int, Iterable[int]],
    *,
    after_left: int,
    column_right: int,
    row_top: int | None = None,
    known_bottom_before: int | None = None,
) -> LiveCandidateCheck:
    """Verify one placed glyph against the dynamic residual left profile.

    The candidate already has an absolute placement. We walk every raster row
    in its own vertical extent and apply left-dominance rules:

    * expected glyph pixels must exist;
    * residual front == expected left edge => ``front``;
    * residual front genuinely left of the candidate's own x span => ``hidden``;
    * residual front inside the candidate span but left of the expected edge is
      a contradiction: the candidate required a profile change that did not
      happen;
    * residual front farther right, or no residual row, contradicts expected ink;
    * an internal horizontal gap must be blank inside the candidate's own x span.

    Candidate edges are terminal profile events only against raster extent that
    was known before this candidate was tried.  At the top, ``row_top`` is the
    known row boundary: if the candidate touches it, no upward terminal event is
    required.  At the bottom, ``known_bottom_before`` is the previous temporary
    lower extent: if the candidate reaches or extends beyond it, no downward
    terminal event is required.  Otherwise the first next profile pixel across
    that known edge must be strictly to the right of the candidate's x span.

    Ink farther right is irrelevant. Ink farther left can belong to another
    overlapping glyph only when it lies outside this candidate's own span.
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
        residual_xs = _residual_row(
            remaining_by_y,
            page_y,
            after_left=after_left,
            column_right=column_right,
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
            continue

        if observed_left >= span_left:
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=page_y,
            )
        hidden_rows += 1

    candidate_top = candidate.baseline + rel_top
    candidate_bottom = candidate.baseline + rel_bottom

    # The upper edge is testable only if there was already known row extent
    # above it. A glyph touching row_top can have arrived directly from geometry
    # in the preceding row, so there is no required upward terminal event.
    if row_top is not None and candidate_top > int(row_top):
        terminal_ok, event_y = _terminal_event_holds(
            remaining_by_y,
            range(candidate_top - 1, int(row_top) - 1, -1),
            after_left=after_left,
            column_right=column_right,
            span_right=span_right,
        )
        if not terminal_ok:
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=event_y,
            )

    # Symmetrically, the lower edge is testable only inside the extent that was
    # already known before this candidate. A candidate that reaches or extends
    # below the previous temporary bottom is itself discovering that territory,
    # so it must not be rejected for lacking a downward terminal event there.
    if known_bottom_before is not None and candidate_bottom < int(known_bottom_before):
        terminal_ok, event_y = _terminal_event_holds(
            remaining_by_y,
            range(candidate_bottom + 1, int(known_bottom_before) + 1),
            after_left=after_left,
            column_right=column_right,
            span_right=span_right,
        )
        if not terminal_ok:
            return LiveCandidateCheck(
                candidate=candidate,
                alive=False,
                front_rows=front_rows,
                hidden_rows=hidden_rows,
                gap_rows=gap_rows,
                contradiction_y=event_y,
            )

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
    row_top: int | None = None,
    known_bottom_before: int | None = None,
) -> tuple[LiveCandidateCheck, ...]:
    checks = [
        check_live_candidate(
            candidate,
            remaining_by_y,
            after_left=after_left,
            column_right=column_right,
            row_top=row_top,
            known_bottom_before=known_bottom_before,
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


def pick_unique_live_semantic(
    candidates: Iterable[BaselineMatch],
    remaining_by_y: Mapping[int, Iterable[int]],
    *,
    after_left: int,
    column_right: int,
    row_top: int | None = None,
    known_bottom_before: int | None = None,
) -> tuple[BaselineMatch | None, tuple[LiveCandidateCheck, ...]]:
    """Return a glyph only when one leftmost semantic interpretation survives."""
    survivors = live_survivors(
        candidates,
        remaining_by_y,
        after_left=after_left,
        column_right=column_right,
        row_top=row_top,
        known_bottom_before=known_bottom_before,
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
        return None, left_group

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
