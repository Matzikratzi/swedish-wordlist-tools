from __future__ import annotations

"""Restore the conservative full baseline race after the pruning experiment.

The pruning experiment proved that racing many baseline hypotheses dominates
runtime, but choosing a winner after one substantial glyph was not safe.  Keep
the useful per-baseline walk cache and small-glyph rejection while restoring the
last known-correct rule: every verified candidate runs to completion and final
row scores decide the winner.
"""

from . import ocr_sequential_raw_page_rows as _scanner
from . import ocr_sequential_raw_page_rows_homonymfix as _previous


def _race_baselines(
    raw: set[tuple[int, int]],
    baselines,
    models,
    left: int,
    right: int,
    anchor_x: int,
    *,
    first_candidates_by_baseline=None,
):
    page_candidates = _scanner.cached._bound_page_candidates(models)
    states: list[_previous._RaceState] = []
    for baseline in sorted(set(int(b) for b in baselines)):
        first_candidates = None
        if first_candidates_by_baseline is not None:
            first_candidates = first_candidates_by_baseline.get(baseline)
            if not first_candidates:
                continue
        states.append(
            _previous._RaceState(
                baseline=baseline,
                cursor=int(anchor_x),
                matched_right=int(anchor_x),
                remaining=set(raw),
                first_candidates=first_candidates,
            )
        )

    active = list(states)
    rounds = 0
    while active:
        rounds += 1
        next_active = []
        for state in active:
            if _previous._advance_one(state, page_candidates, left=left, right=right):
                next_active.append(state)
        active = next_active

    print(
        "raw-page-baseline-race: "
        f"x={anchor_x} rounds={rounds} "
        + ", ".join(
            f"b={state.baseline}:glyphs={state.matched_glyphs}:right={state.matched_right}:verified={state.baseline_verified}"
            for state in states
        )
    )

    results = {}
    for state in states:
        if state.matched_glyphs <= 0 or not state.owned or not state.baseline_verified:
            continue
        result = (
            state.matched_glyphs,
            set(state.owned),
            state.matched_right,
        )
        _previous._remember_walk(
            raw,
            state.baseline,
            left,
            right,
            anchor_x,
            state.first_candidates,
            None,
            result,
        )
        results[state.baseline] = result
    return results


def _ordinary_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
    first_candidates,
):
    """Generate exact baseline hypotheses, then conservatively race them."""
    hypotheses: set[int] = set()
    anchor_bottom = min(search_limit, search_from + _scanner.START_SEARCH_HEIGHT)
    for anchor_y in range(search_from, anchor_bottom):
        if (anchor_x, anchor_y) not in raw:
            continue
        for model, min_x, left_pixels in first_candidates:
            x0 = anchor_x - min_x
            if x0 < left or x0 + model.width > right:
                continue
            for _mx, my in left_pixels:
                baseline = anchor_y - my
                if baseline < search_from or baseline >= search_limit:
                    continue
                placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                if placed and placed.issubset(raw):
                    hypotheses.add(baseline)

    exact_by_baseline = {}
    for baseline in sorted(hypotheses):
        exact_first = _scanner._exact_first_candidates(
            raw,
            baseline,
            first_candidates,
            anchor_x,
            left,
            right,
        )
        if exact_first:
            exact_by_baseline[baseline] = exact_first

    raced = _race_baselines(
        raw,
        exact_by_baseline,
        models,
        left,
        right,
        anchor_x,
        first_candidates_by_baseline=exact_by_baseline,
    )
    walks = {}
    for baseline, (glyphs, owned, matched_right) in raced.items():
        score = (matched_right - anchor_x, glyphs, len(owned))
        walks[(anchor_x, baseline)] = (
            score,
            None,
            anchor_x,
            owned,
            glyphs,
            matched_right,
        )

    if walks:
        diagnostics = ", ".join(
            f"b={baseline}:score={item[0]}"
            for (_x, baseline), item in sorted(walks.items())
        )
        print(f"raw-page-full-row-baseline-candidates: {diagnostics}")
    return walks


# Functions in homonymfix resolve _race_baselines at call time, so replacing
# this global also restores its page-1/local-x-first paths without duplicating
# those functions here.
_previous._race_baselines = _race_baselines
_scanner._ordinary_baseline_probe_walks = _ordinary_baseline_probe_walks
