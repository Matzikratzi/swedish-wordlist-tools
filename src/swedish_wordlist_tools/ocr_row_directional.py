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
) -> tuple[BaselineMatch, ...]:
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


def _trace_candidate(prefix: str, event: str, candidate: BaselineMatch, **fields: object) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items())
    print(
        f"{prefix} first-glyph-{event}: label={candidate.model.label!r} style={candidate.model.style} "
        f"left={candidate.left} right={candidate.right} baseline={candidate.baseline} "
        f"discovered_y={candidate.discovered_y} pixels={len(candidate.pixels)}"
        + (f" {extra}" if extra else ""),
        flush=True,
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
    trace: bool = False,
    trace_prefix: str = "directional-trace",
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
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
    previous_profile_x: int | None = None

    for page_y in range(row_top, scan_bottom):
        if left_profile is None:
            row_xs = tuple(sorted(black_by_y.get(page_y, ())))
            profile_x = row_xs[0] if row_xs else None
        else:
            profile_x = left_profile.at(page_y)
        profile_history[page_y] = profile_x

        if trace and profile_x is not None:
            print(
                f"{trace_prefix} first-glyph-profile: y={page_y} x={profile_x} prev={previous_profile_x} "
                f"active={len(active)} passed={len(passed)} allowed={_x_allowed(profile_x, ranges)}",
                flush=True,
            )

        if active:
            next_live: list[BaselineMatch] = []
            next_passed = list(passed)
            for candidate in active:
                state = _advance_candidate(
                    candidate,
                    page_y=page_y,
                    profile_x=profile_x,
                    previous_profile_x=previous_profile_x,
                )
                if trace:
                    _trace_candidate(
                        trace_prefix,
                        state,
                        candidate,
                        y=page_y,
                        profile_x=profile_x,
                        previous_profile_x=previous_profile_x,
                    )
                if state == "live":
                    next_live.append(candidate)
                elif state == "passed":
                    next_passed.append(candidate)

            active = tuple(next_live)
            passed = tuple(next_passed)
            if active:
                previous_profile_x = profile_x if profile_x is not None else previous_profile_x
                continue

            if passed:
                hit = _pick_unique_maximal(passed)
                if trace:
                    print(
                        f"{trace_prefix} first-glyph-pick: y={page_y} passed={len(passed)} "
                        f"accepted={hit.model.label!r if hit is not None else None}",
                        flush=True,
                    )
                return hit, FirstGlyphSearch(y=active_y, candidates=passed)

            active_y = None

        if profile_x is None or not _x_allowed(profile_x, ranges):
            if profile_x is not None:
                previous_profile_x = profile_x
            continue

        proposals = _history_seed_proposals(
            page_y=page_y,
            profile_x=profile_x,
            profile_history=profile_history,
            black=black,
            library=library,
            row_top=row_top,
        )
        if trace:
            print(
                f"{trace_prefix} first-glyph-seed: y={page_y} x={profile_x} proposals={len(proposals)}",
                flush=True,
            )
            for candidate in proposals:
                _trace_candidate(trace_prefix, "proposal", candidate)
        if not proposals:
            previous_profile_x = profile_x
            continue

        if first_trigger_y is None:
            first_trigger_y = page_y
        active = proposals
        passed = ()
        active_y = page_y
        previous_profile_x = profile_x

    candidates = tuple((*passed, *active))
    return None, FirstGlyphSearch(
        y=active_y if active_y is not None else first_trigger_y,
        candidates=candidates,
    )
