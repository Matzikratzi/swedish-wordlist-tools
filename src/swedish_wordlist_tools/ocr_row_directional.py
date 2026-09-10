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


def _row_start_proposals(
    *,
    page_y: int,
    observed_xs: tuple[int, ...],
    black: set[Pixel],
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
) -> tuple[BaselineMatch, ...]:
    proposals: dict[tuple[int, int, int], BaselineMatch] = {}
    for item in library.models:
        top_rel_y = item.model.min_y
        top_row = item.rows[top_rel_y]
        baseline = page_y - top_rel_y
        for observed_x in observed_xs:
            for model_x in top_row:
                tx = observed_x - model_x
                key = (id(item.model), tx, baseline)
                if key in proposals:
                    continue
                placed = _placed_pixels(item, tx=tx, baseline=baseline)
                if not placed.issubset(black):
                    continue

                physical_left = tx + item.min_x
                physical_right = tx + item.max_x
                previous = black_by_y.get(page_y - 1, ())
                if any(physical_left <= x <= physical_right for x in previous):
                    continue

                proposals[key] = BaselineMatch(
                    model=item.model,
                    tx=tx,
                    baseline=baseline,
                    pixels=placed,
                    discovered_y=page_y,
                )

    return tuple(
        sorted(
            proposals.values(),
            key=lambda hit: (
                hit.left,
                hit.discovered_y,
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

    A row-start placement is provisional.  Once candidates are alive, the
    residual left profile is followed row by row and no later row-start glyph
    is proposed until those candidates have either been contradicted or the
    profile has confirmed that it passed them.

    Candidate survival is based on the candidate's own placed raster.  On a
    row where the candidate has pixels, its leftmost placed pixel must own the
    profile front.  Internal blank rows remain undecided.  After its last raster
    row, the first nonblank profile event must move at least one pixel right to
    confirm passage.

    If every live candidate is contradicted, the same profile row that killed
    them is immediately eligible as a new row-start observation.  New
    candidates are still only created when that observed x lies in a permitted
    row-start interval.

    Start intervals are absolute page x coordinates of observed profile pixels,
    not model translation coordinates.

    ``row_bottom`` remains as an optional compatibility/search limit for older
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

    scan_y = tuple(range(row_top, scan_bottom))

    active: tuple[BaselineMatch, ...] = ()
    active_y: int | None = None
    first_y: int | None = None

    for page_y in scan_y:
        if left_profile is None:
            row_xs = tuple(sorted(black_by_y.get(page_y, ())))
            profile_x = row_xs[0] if row_xs else None
        else:
            profile_x = left_profile.at(page_y)
            row_xs = () if profile_x is None else (profile_x,)

        if active:
            live: list[BaselineMatch] = []
            passed: list[BaselineMatch] = []
            for candidate in active:
                state = _advance_candidate(
                    candidate,
                    page_y=page_y,
                    profile_x=profile_x,
                )
                if state == "live":
                    live.append(candidate)
                elif state == "passed":
                    passed.append(candidate)

            if live:
                active = tuple(live)
                continue

            if passed:
                passed_group = tuple(passed)
                hit = _pick_unique_maximal(passed_group)
                return hit, FirstGlyphSearch(
                    y=active_y,
                    candidates=passed_group,
                )

            # All active candidates were contradicted.  Reuse this exact
            # profile row as a possible start of the real first glyph.
            active = ()
            active_y = None

        observed_xs = tuple(x for x in row_xs if _x_allowed(x, ranges))
        if not observed_xs:
            continue

        proposals = _row_start_proposals(
            page_y=page_y,
            observed_xs=observed_xs,
            black=black,
            black_by_y=black_by_y,
            library=library,
        )
        if not proposals:
            continue

        if first_y is None:
            first_y = page_y

        left = min(hit.left for hit in proposals)
        active = tuple(hit for hit in proposals if hit.left == left)
        active_y = page_y

    if not active:
        return None, FirstGlyphSearch(y=first_y, candidates=())

    return None, FirstGlyphSearch(
        y=active_y,
        candidates=active,
    )
