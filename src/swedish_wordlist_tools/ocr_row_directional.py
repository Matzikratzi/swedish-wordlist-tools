from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_baseline_up import BaselineMatch, CompiledGlyph, CompiledGlyphLibrary, Pixel
from .ocr_column_left_profile import ColumnLeftProfile


TranslateXRange = tuple[int, int]


@dataclass(frozen=True)
class FirstGlyphSearch:
    y: int | None
    candidates: tuple[BaselineMatch, ...]


def _x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


def _placed_pixels(item: CompiledGlyph, *, tx: int, baseline: int) -> frozenset[Pixel]:
    return frozenset((tx + x, baseline + y) for x, y in item.model.pixels)


def _pick_unique_maximal(candidates: Iterable[BaselineMatch]) -> BaselineMatch | None:
    rows = list(candidates)
    if not rows:
        return None
    maximal = [
        hit
        for hit in rows
        if not any(hit.pixels < other.pixels for other in rows if other is not hit)
    ]
    distinct = {hit.pixels for hit in maximal}
    if len(distinct) != 1:
        return None
    target = next(iter(distinct))
    equivalent = [hit for hit in maximal if hit.pixels == target]
    return max(equivalent, key=lambda hit: (len(hit.pixels), hit.model.sources))


def _candidate_rows(candidate: BaselineMatch) -> dict[int, tuple[int, ...]]:
    rows: dict[int, list[int]] = {}
    for x, y in candidate.pixels:
        rows.setdefault(y, []).append(x)
    return {y: tuple(sorted(xs)) for y, xs in rows.items()}


def _candidate_last_front(candidate: BaselineMatch) -> int:
    rows = _candidate_rows(candidate)
    last_y = max(rows)
    return rows[last_y][0]


def _candidate_matches_seen_profile(
    candidate: BaselineMatch,
    profile_history: Mapping[int, int | None],
    *,
    through_y: int,
) -> bool:
    """Return whether the candidate agrees with every one of its seen rows.

    Profile history may start before the glyph itself; those earlier pixels are
    intentionally irrelevant.  Likewise an internal raster row on which the
    glyph has no pixels does not have to own the page profile.  But whenever
    the candidate has pixels on a row that has already been observed, its own
    leftmost pixel must be the page's left profile on that row.
    """
    for page_y, xs in _candidate_rows(candidate).items():
        if page_y > through_y:
            continue
        observed = profile_history.get(page_y)
        if observed is None or observed != xs[0]:
            return False
    return True


def _candidate_explains_left_ink_to_baseline(
    candidate: BaselineMatch,
    black: set[Pixel],
) -> bool:
    """Reject a first-glyph placement that skips unexplained ink to baseline.

    The trigger row gives both the current left-profile front and, via the
    candidate placement, a baseline.  A candidate that really is the first
    glyph may have its own raster extending down and left from that trigger,
    but it may not leave *other* black pixels behind in the already-passed
    left-side region before the baseline is reached.

    We therefore inspect the rectangle from the discovery row through the
    candidate baseline and from the column's left side through the candidate's
    own left-profile front on the discovery row.  Every black pixel there must
    belong to the candidate itself.  This is purely geometric and contains no
    label/style/page/row special case.
    """
    rows = _candidate_rows(candidate)
    trigger_xs = rows.get(candidate.discovered_y)
    if not trigger_xs:
        return False
    trigger_front = trigger_xs[0]

    for x, y in black:
        if y < candidate.discovered_y or y > candidate.baseline:
            continue
        if x > trigger_front:
            continue
        if (x, y) not in candidate.pixels:
            return False
    return True


def _advance_candidate(
    candidate: BaselineMatch,
    *,
    page_y: int,
    profile_x: int | None,
) -> str:
    """Advance one provisional first-glyph candidate by one profile row.

    Return ``live``, ``dead`` or ``passed``.

    While the candidate still has raster geometry, its own leftmost pixel on
    each occupied row must own the residual left profile.  Internal blank rows
    do not decide the candidate: it stays live until its complete raster has
    had a chance to appear.

    After the candidate's final raster row, the first later nonblank profile
    event decides it.  For now we deliberately use the weakest terminal rule:
    one step to the right of the candidate's last owned profile pixel confirms
    that the profile has passed it.  A front at the same x or to the left
    contradicts it.

    This is purely geometric; it contains no glyph-, style-, row- or
    page-specific cases.
    """
    rows = _candidate_rows(candidate)
    bottom = max(rows)

    if page_y <= bottom:
        candidate_xs = rows.get(page_y)
        if candidate_xs is None:
            return "live"
        if profile_x is None:
            return "dead"
        return "live" if profile_x == candidate_xs[0] else "dead"

    if profile_x is None:
        return "live"
    return "passed" if profile_x > _candidate_last_front(candidate) else "dead"


def _history_seed_proposals(
    *,
    page_y: int,
    profile_x: int,
    profile_history: Mapping[int, int | None],
    black: set[Pixel],
    library: CompiledGlyphLibrary,
    row_top: int,
) -> tuple[BaselineMatch, ...]:
    """Seed all exact glyphs whose already-seen profile fits upward.

    ``page_y`` is only a trigger row: it need not be the glyph's top row and
    ``profile_x`` need not be the glyph's physical left edge.  Every occupied
    model row is allowed to align with the trigger.  The resulting placement
    must fit the page raster, must not begin above the known row boundary, and
    must agree with all candidate-owned profile rows that have already been
    observed.  Profile observations before the candidate begins are allowed to
    remain unexplained at this stage.

    Once the placement establishes a baseline, it must also explain all black
    pixels in the already-passed left-side region from the trigger row down to
    that baseline.  This prevents a short high candidate from jumping over the
    lower part of a taller first glyph.
    """
    proposals: dict[tuple[int, int, int], BaselineMatch] = {}

    for item in library.models:
        for rel_y, model_row in item.rows.items():
            row_left = min(model_row)
            tx = profile_x - row_left
            baseline = page_y - rel_y
            key = (id(item.model), tx, baseline)
            if key in proposals:
                continue

            placed = _placed_pixels(item, tx=tx, baseline=baseline)
            if not placed or min(y for _x, y in placed) < row_top:
                continue
            if not placed.issubset(black):
                continue

            candidate = BaselineMatch(
                model=item.model,
                tx=tx,
                baseline=baseline,
                pixels=placed,
                discovered_y=page_y,
            )
            if not _candidate_matches_seen_profile(
                candidate,
                profile_history,
                through_y=page_y,
            ):
                continue
            if not _candidate_explains_left_ink_to_baseline(candidate, black):
                continue
            proposals[key] = candidate

    return tuple(
        sorted(
            proposals.values(),
            key=lambda hit: (
                hit.discovered_y,
                hit.baseline,
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )


def first_glyph_top_down(
    black: set[Pixel],
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    row_top: int,
    row_bottom: int | None = None,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    left_profile: ColumnLeftProfile | None = None,
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the first glyph from the known upper row boundary.

    The page profile is remembered from ``row_top`` downward.  Entering a legal
    row-start x interval is a *trigger*, not an assertion that the current
    profile pixel is the top or physical left edge of the first glyph.  At that
    point every exact facit placement whose already-seen left profile fits
    upward is admitted as a provisional candidate.  Older profile pixels may
    extend above the glyph and remain unexplained.

    Once candidates exist we stop discovering new ones and follow only that
    live set downward.  On each occupied candidate row its own leftmost pixel
    must continue to own the page profile.  Internal blank rows do not kill the
    candidate.  After the candidate's last raster row, one profile step to the
    right is enough for now to mark it passed; staying at or moving left kills
    it.  Passed candidates are retained while any other candidate is still
    live, so a short glyph cannot win merely because it ended first.

    If all live candidates die with no passed candidate, scanning resumes and
    the killing row remains in profile history.  There are no glyph-, style-,
    row- or page-specific cases here.

    ``row_bottom`` remains an optional compatibility/search limit for older
    callers and focused tests.  New sequential page OCR should leave it unset.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return None, FirstGlyphSearch(y=None, candidates=())

    if row_bottom is None:
        if left_profile is not None:
            scan_bottom = left_profile.bottom
        elif black_by_y:
            scan_bottom = max(black_by_y) + 1
        else:
            return None, FirstGlyphSearch(y=None, candidates=())
    else:
        scan_bottom = int(row_bottom)
    if scan_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    profile_history: dict[int, int | None] = {}
    active: tuple[BaselineMatch, ...] = ()
    passed: tuple[BaselineMatch, ...] = ()
    active_y: int | None = None
    first_trigger_y: int | None = None

    for page_y in range(row_top, scan_bottom):
        if left_profile is None:
            row_xs = tuple(sorted(black_by_y.get(page_y, ())))
            profile_x = row_xs[0] if row_xs else None
        else:
            profile_x = left_profile.at(page_y)
        profile_history[page_y] = profile_x

        if active:
            next_live: list[BaselineMatch] = []
            next_passed = list(passed)
            for candidate in active:
                state = _advance_candidate(
                    candidate,
                    page_y=page_y,
                    profile_x=profile_x,
                )
                if state == "live":
                    next_live.append(candidate)
                elif state == "passed":
                    next_passed.append(candidate)

            active = tuple(next_live)
            passed = tuple(next_passed)
            if active:
                continue

            if passed:
                hit = _pick_unique_maximal(passed)
                return hit, FirstGlyphSearch(
                    y=active_y,
                    candidates=passed,
                )

            active_y = None

        if profile_x is None or not _x_allowed(profile_x, ranges):
            continue

        proposals = _history_seed_proposals(
            page_y=page_y,
            profile_x=profile_x,
            profile_history=profile_history,
            black=black,
            library=library,
            row_top=row_top,
        )
        if not proposals:
            continue

        if first_trigger_y is None:
            first_trigger_y = page_y
        active = proposals
        passed = ()
        active_y = page_y

    candidates = tuple((*passed, *active))
    return None, FirstGlyphSearch(
        y=active_y if active_y is not None else first_trigger_y,
        candidates=candidates,
    )
