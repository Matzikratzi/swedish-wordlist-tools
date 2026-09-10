from __future__ import annotations

import os
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
    previous_profile_x: int | None = None,
) -> str:
    rows = _candidate_rows(candidate)
    bottom = max(rows)

    if page_y <= bottom:
        candidate_xs = rows.get(page_y)
        if candidate_xs is not None:
            if profile_x is None:
                return "dead"
            return "live" if profile_x == candidate_xs[0] else "dead"

        if (
            profile_x is not None
            and previous_profile_x is not None
            and profile_x < previous_profile_x
        ):
            return "dead"
        return "live"

    if profile_x is None:
        return "live"
    if previous_profile_x is not None and profile_x < previous_profile_x:
        return "dead"
    return "passed" if profile_x > _candidate_last_front(candidate) else "dead"


def _history_seed_proposals(
    *,
    page_y: int,
    profile_x: int,
    profile_history: Mapping[int, int | None],
    black: set[Pixel],
    library: CompiledGlyphLibrary,
    row_top: int,
    start_ranges: tuple[TranslateXRange, ...],
) -> tuple[BaselineMatch, ...]:
    """Legacy single-observation seeding kept for comparison/debugging."""
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
            if not _x_allowed(candidate.left, start_ranges):
                continue
            if not _candidate_matches_seen_profile(candidate, profile_history, through_y=page_y):
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


def _profile_at(
    page_y: int,
    *,
    black_by_y: Mapping[int, Iterable[int]],
    left_profile: ColumnLeftProfile | None,
) -> int | None:
    if left_profile is not None:
        return left_profile.at(page_y)
    row_xs = tuple(black_by_y.get(page_y, ()))
    return min(row_xs) if row_xs else None


def _two_row_profile_proposals(
    *,
    anchor_y: int,
    neighbour_y: int,
    anchor_x: int,
    neighbour_x: int,
    black: set[Pixel],
    library: CompiledGlyphLibrary,
    row_top: int,
    start_ranges: tuple[TranslateXRange, ...],
) -> tuple[BaselineMatch, ...]:
    """Place glyphs only after two adjacent residual profile rows agree.

    The leftmost residual pixel chooses the first observation. A single point
    is intentionally insufficient: almost every glyph can be translated
    through one point. The adjacent residual row supplies the profile
    slope/event needed to constrain both translation and baseline. Only
    placements that explain both left-profile pixels are materialised and
    subjected to the exact 2-D subset check.
    """
    dy = neighbour_y - anchor_y
    if dy not in (-1, 1):
        raise ValueError("profile neighbour must be exactly one y step away")

    proposals: dict[tuple[int, int, int], BaselineMatch] = {}
    for item in library.models:
        for rel_y, model_row in item.rows.items():
            neighbour_rel_y = rel_y + dy
            neighbour_row = item.rows.get(neighbour_rel_y)
            if neighbour_row is None:
                continue

            model_x = model_row[0]
            neighbour_model_x = neighbour_row[0]
            if neighbour_model_x - model_x != neighbour_x - anchor_x:
                continue

            tx = anchor_x - model_x
            baseline = anchor_y - rel_y
            key = (id(item.model), tx, baseline)
            if key in proposals:
                continue

            physical_left = tx + item.min_x
            if not _x_allowed(physical_left, start_ranges):
                continue

            placed = _placed_pixels(item, tx=tx, baseline=baseline)
            if not placed or min(y for _x, y in placed) < row_top:
                continue
            if (anchor_x, anchor_y) not in placed or (neighbour_x, neighbour_y) not in placed:
                continue
            if not placed.issubset(black):
                continue

            proposals[key] = BaselineMatch(
                model=item.model,
                tx=tx,
                baseline=baseline,
                pixels=placed,
                discovered_y=anchor_y,
            )

    return tuple(
        sorted(
            proposals.values(),
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
                hit.baseline,
            ),
        )
    )


def _trace_candidate(prefix: str, event: str, candidate: BaselineMatch, **fields: object) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"{prefix} first-glyph-{event}: label={candidate.model.label!r} style={candidate.model.style} "
        f"left={candidate.left} right={candidate.right} baseline={candidate.baseline} "
        f"discovered_y={candidate.discovered_y} pixels={len(candidate.pixels)}"
        + (f" {extra}" if extra else ""),
        flush=True,
    )


def _default_scan_bottom(
    *,
    row_top: int,
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    left_profile: ColumnLeftProfile | None,
) -> int:
    """Bound unknown first-row height using glyph geometry, never facit rows."""
    source_bottom = (
        left_profile.bottom
        if left_profile is not None
        else (max(black_by_y) + 1 if black_by_y else row_top)
    )
    max_glyph_height = max(
        (max(item.rows) - min(item.rows) + 1 for item in library.models if item.rows),
        default=1,
    )
    return min(source_bottom, row_top + max_glyph_height)


def first_glyph_top_down(
    black: set[Pixel],
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    row_top: int,
    row_bottom: int | None = None,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    left_profile: ColumnLeftProfile | None = None,
    trace: bool = False,
    trace_prefix: str = "directional-trace",
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the first glyph from the row-local leftmost edge and a y-neighbour.

    The anchor is the smallest residual x inside a row-local scan band. When
    the caller does not know row_bottom, the band is bounded by the maximum
    compiled glyph height from row_top. This keeps the search on the current
    text row without using reference/facit row geometry.
    """
    trace = trace or os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return None, FirstGlyphSearch(y=None, candidates=())

    if row_bottom is None:
        scan_bottom = _default_scan_bottom(
            row_top=row_top,
            black_by_y=black_by_y,
            library=library,
            left_profile=left_profile,
        )
    else:
        scan_bottom = int(row_bottom)
    if scan_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    profile: dict[int, int] = {}
    for page_y in range(row_top, scan_bottom):
        x = _profile_at(page_y, black_by_y=black_by_y, left_profile=left_profile)
        if x is not None:
            profile[page_y] = x
    if not profile:
        return None, FirstGlyphSearch(y=None, candidates=())

    leftmost_x = min(profile.values())
    anchor_ys = tuple(y for y, x in sorted(profile.items()) if x == leftmost_x)

    if trace:
        print(
            f"{trace_prefix} first-glyph-leftmost: band={row_top}..{scan_bottom - 1} "
            f"x={leftmost_x} ys={anchor_ys}",
            flush=True,
        )

    all_proposals: dict[tuple[int, int, int], BaselineMatch] = {}
    used_anchor_y: int | None = None

    for anchor_y in anchor_ys:
        for neighbour_y in (anchor_y + 1, anchor_y - 1):
            if neighbour_y < row_top or neighbour_y >= scan_bottom:
                continue
            neighbour_x = profile.get(neighbour_y)
            if neighbour_x is None:
                continue

            proposals = _two_row_profile_proposals(
                anchor_y=anchor_y,
                neighbour_y=neighbour_y,
                anchor_x=leftmost_x,
                neighbour_x=neighbour_x,
                black=black,
                library=library,
                row_top=row_top,
                start_ranges=ranges,
            )
            if trace:
                direction = "down" if neighbour_y > anchor_y else "up"
                print(
                    f"{trace_prefix} first-glyph-pair: anchor=({leftmost_x},{anchor_y}) "
                    f"{direction}=({neighbour_x},{neighbour_y}) proposals={len(proposals)}",
                    flush=True,
                )
                for candidate in proposals:
                    _trace_candidate(trace_prefix, "proposal", candidate)

            if proposals and used_anchor_y is None:
                used_anchor_y = anchor_y
            for candidate in proposals:
                all_proposals[(id(candidate.model), candidate.tx, candidate.baseline)] = candidate

    candidates = tuple(
        sorted(
            all_proposals.values(),
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
                hit.baseline,
            ),
        )
    )
    hit = _pick_unique_maximal(candidates)

    if trace:
        accepted = repr(hit.model.label) if hit is not None else None
        print(
            f"{trace_prefix} first-glyph-pick: leftmost_x={leftmost_x} "
            f"candidates={len(candidates)} accepted={accepted}",
            flush=True,
        )

    return hit, FirstGlyphSearch(y=used_anchor_y, candidates=candidates)
