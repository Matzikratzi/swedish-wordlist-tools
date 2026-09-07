from __future__ import annotations

"""Experimental row matcher with a deliberately open lower boundary.

This module is observational only.  It keeps one row baseline, accepts only
pixel-exact facit placements, permits unexplained ink below/around them, and
continues matching further to the right.  Candidate sets are ranked
lexicographically: explain as much ink at/above the baseline as possible first,
then as much total/deeper ink as possible.
"""

from collections import defaultdict
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, Match


def _anchored_exact_candidates(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    allowed_baselines: set[int] | None = None,
) -> list[Match]:
    """Generate every exact placement, anchoring model left ink to source ink.

    Unlike the normal exact-cover fast path this never requires the rest of the
    source row to be explainable.  A failed local area therefore does not stop
    candidate generation further to the right.
    """
    if not ink:
        return []

    ys_by_x: dict[int, list[int]] = defaultdict(list)
    for x, y in ink:
        ys_by_x[int(x)].append(int(y))
    for ys in ys_by_x.values():
        ys.sort()

    prepared: list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]] = []
    for model in models:
        if not model.pixels:
            continue
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple((x, y) for x, y in model.pixels if x == min_x)
        prepared.append((model, min_x, left_pixels))

    out: list[Match] = []
    seen: set[tuple[str, str, int, int, frozenset[tuple[int, int]]]] = set()
    for anchor_x in sorted(ys_by_x):
        source_ys = ys_by_x[anchor_x]
        for model, min_x, left_pixels in prepared:
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            b_lo = -model.min_y
            b_hi = height - 1 - model.max_y
            candidate_baselines: set[int] = set()
            for _mx, my in left_pixels:
                for source_y in source_ys:
                    baseline = source_y - my
                    if baseline < b_lo or baseline > b_hi:
                        continue
                    if allowed_baselines is not None and baseline not in allowed_baselines:
                        continue
                    candidate_baselines.add(baseline)
            for baseline in sorted(candidate_baselines):
                placed = frozenset(
                    (x0 + x, baseline + y)
                    for x, y in model.pixels
                )
                if not placed.issubset(ink):
                    continue
                key = (model.label, model.style, x0, baseline, placed)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Match(
                        label=model.label,
                        style=model.style,
                        x=x0,
                        baseline=baseline,
                        pixels=placed,
                        model_pixels=len(model.pixels),
                        sources=model.sources,
                    )
                )
    return out


def _selection_key(
    chosen: tuple[Match, ...],
    occupied: frozenset[tuple[int, int]],
    baseline: int,
) -> tuple[int, int, int, int, int, int]:
    above = sum(1 for _x, y in occupied if y <= baseline)
    below = len(occupied) - above
    right = max((x for x, _y in occupied), default=-1)
    return (
        above,
        len(occupied),
        below,
        right,
        sum(match.sources for match in chosen),
        -len(chosen),
    )


def _best_disjoint_for_baseline(
    matches: list[Match],
    baseline: int,
    *,
    beam_width: int,
) -> tuple[Match, ...]:
    rows = sorted(
        matches,
        key=lambda match: (
            match.x,
            -match.model_pixels,
            -max(y for _x, y in match.pixels),
            -match.sources,
            match.label,
            match.style,
        ),
    )
    states: list[tuple[tuple[Match, ...], frozenset[tuple[int, int]]]] = [
        ((), frozenset())
    ]
    for match in rows:
        expanded = list(states)
        for chosen, occupied in states:
            if occupied.intersection(match.pixels):
                continue
            expanded.append(
                (
                    chosen + (match,),
                    frozenset(set(occupied) | set(match.pixels)),
                )
            )
        best_by_occupied: dict[frozenset[tuple[int, int]], tuple[Match, ...]] = {}
        for chosen, occupied in expanded:
            previous = best_by_occupied.get(occupied)
            if previous is None or _selection_key(chosen, occupied, baseline) > _selection_key(
                previous, occupied, baseline
            ):
                best_by_occupied[occupied] = chosen
        states = sorted(
            ((chosen, occupied) for occupied, chosen in best_by_occupied.items()),
            key=lambda state: _selection_key(state[0], state[1], baseline),
            reverse=True,
        )[:beam_width]
    if not states:
        return ()
    return max(states, key=lambda state: _selection_key(state[0], state[1], baseline))[0]


def probe_open_bottom(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    baseline_hint: int | None = None,
    baseline_radius: int = 1,
    beam_width: int = 128,
) -> dict:
    """Find the strongest same-baseline exact evidence with residual ink allowed.

    When a baseline hint is available the experiment intentionally tests only
    that baseline +/- ``baseline_radius``.  This isolates the open-bottom idea
    from the separate problem of discovering the row baseline.
    """
    if baseline_radius < 0:
        raise ValueError("baseline_radius must be >= 0")
    allowed = None
    if baseline_hint is not None:
        allowed = {
            int(baseline_hint) + delta
            for delta in range(-int(baseline_radius), int(baseline_radius) + 1)
        }

    candidates = _anchored_exact_candidates(
        ink,
        width,
        height,
        models,
        allowed_baselines=allowed,
    )
    by_baseline: dict[int, list[Match]] = defaultdict(list)
    for match in candidates:
        by_baseline[match.baseline].append(match)

    best_baseline: int | None = None
    best_selected: tuple[Match, ...] = ()
    best_key: tuple[int, int, int, int, int, int] | None = None
    for baseline in sorted(by_baseline):
        selected = _best_disjoint_for_baseline(
            by_baseline[baseline], baseline, beam_width=beam_width
        )
        occupied = frozenset().union(*(match.pixels for match in selected)) if selected else frozenset()
        key = _selection_key(selected, occupied, baseline)
        if best_key is None or key > best_key:
            best_key = key
            best_baseline = baseline
            best_selected = selected

    covered = set().union(*(match.pixels for match in best_selected)) if best_selected else set()
    baseline = best_baseline
    source_above = sum(1 for _x, y in ink if baseline is not None and y <= baseline)
    covered_above = sum(1 for _x, y in covered if baseline is not None and y <= baseline)
    source_below = len(ink) - source_above if baseline is not None else len(ink)
    covered_below = len(covered) - covered_above
    return {
        "baseline": baseline,
        "candidate_count": len(candidates),
        "selected": sorted(
            best_selected,
            key=lambda match: (match.x, match.baseline, match.label, match.style),
        ),
        "covered_pixels": len(covered),
        "source_pixels": len(ink),
        "source_above": source_above,
        "covered_above": covered_above,
        "unmatched_above": source_above - covered_above,
        "source_below": source_below,
        "covered_below": covered_below,
        "unmatched_below": source_below - covered_below,
        "rightmost_covered_x": max((x for x, _y in covered), default=-1),
    }
