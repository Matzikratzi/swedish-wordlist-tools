from __future__ import annotations

"""Restore the conservative full baseline race after the pruning experiment.

The pruning experiment proved that racing many baseline hypotheses dominates
runtime, but choosing a winner after one substantial glyph was not safe. Keep
the useful per-baseline walk cache and small-glyph rejection while restoring the
last known-correct rule: every verified candidate runs to completion and final
row scores decide the winner.

Facit placement tests are deliberately short-circuited: as soon as one required
facit pixel is absent from source ink, that placement is rejected. A ``set`` of
placed pixels is only materialized for a successful match. This is intended to
be decision-identical to ``placed.issubset(raw)`` while avoiding allocations for
the overwhelmingly common failed placements.
"""

from . import ocr_sequential_raw_page_rows as _scanner
from . import ocr_sequential_raw_page_rows_homonymfix as _previous


def _placed_if_subset(model, x0: int, baseline: int, raw):
    """Return placed facit pixels if all exist in raw; otherwise fail early."""
    for mx, my in model.pixels:
        if (x0 + mx, baseline + my) not in raw:
            return None
    if not model.pixels:
        return None
    return {(x0 + mx, baseline + my) for mx, my in model.pixels}


def _advance_one(
    state: _previous._RaceState,
    page_candidates,
    *,
    left: int,
    right: int,
) -> bool:
    """Decision-identical race step with early rejection of failed facit tests."""
    while state.cursor < right:
        if state.matched_glyphs == 0 and state.first_candidates is not None:
            candidates = state.first_candidates
        else:
            candidates = _scanner.cached._iter_candidates(
                page_candidates,
                first_glyph=state.matched_glyphs == 0,
                previous_style=state.previous_style,
                row_kind="unknown",
                leading_homonym_seen=False,
                baseline_established=True,
            )

        chosen = None
        blocked_small = None
        for model, min_x, _left_pixels in candidates:
            x0 = state.cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = _placed_if_subset(model, x0, state.baseline, state.remaining)
            if placed is None:
                continue

            is_small = len(placed) <= _previous._SMALL_GLYPH_MAX_PIXELS
            if (
                not state.baseline_verified
                and is_small
                and state.leading_small_glyphs >= _previous._MAX_LEADING_SMALL_GLYPHS
            ):
                if blocked_small is None:
                    blocked_small = (model, placed, x0)
                continue

            chosen = (model, placed, x0)
            break

        if chosen is not None:
            model, placed, x0 = chosen
            state.remaining.difference_update(placed)
            state.owned.update(placed)
            state.matched_glyphs += 1
            if not state.baseline_verified:
                if len(placed) <= _previous._SMALL_GLYPH_MAX_PIXELS:
                    state.leading_small_glyphs += 1
                else:
                    state.baseline_verified = True
            state.previous_style = _scanner.priority._typographic_style(model.style)
            glyph_right = max(px for px, _py in placed) + 1
            state.matched_right = max(state.matched_right, glyph_right)
            state.cursor = max(state.cursor + 1, glyph_right)
            return True

        if blocked_small is not None:
            model, placed, x0 = blocked_small
            print(
                "raw-page-baseline-reject-small-run: "
                f"b={state.baseline} after={state.leading_small_glyphs} "
                f"x0={x0} label={model.label!r} pixels={len(placed)}"
            )
            state.exhausted = True
            return False

        later_x = [x for x, _y in state.remaining if x > state.cursor]
        if not later_x:
            state.exhausted = True
            return False
        state.cursor = min(later_x)

    state.exhausted = True
    return False


def _exact_first_candidates(raw, baseline, candidates, anchor_x, left, right):
    """Same exact-first ordering, but reject failed models before allocating sets."""
    exact = []
    for candidate in candidates:
        model, min_x, _left_pixels = candidate
        x0 = anchor_x - min_x
        if x0 < left or x0 + model.width > right:
            continue
        placed = _placed_if_subset(model, x0, baseline, raw)
        if placed is not None:
            exact.append((len(placed), candidate))
    exact.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _pixels, candidate in exact]


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
            if _advance_one(state, page_candidates, left=left, right=right):
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
                if _placed_if_subset(model, x0, baseline, raw) is not None:
                    hypotheses.add(baseline)

    exact_by_baseline = {}
    for baseline in sorted(hypotheses):
        exact_first = _exact_first_candidates(
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


# Functions in homonymfix resolve these globals at call time. Install the
# conservative race plus the allocation-free failed-placement tests without
# changing any scoring or winner selection rule.
_previous._advance_one = _advance_one
_previous._race_baselines = _race_baselines
_scanner._exact_first_candidates = _exact_first_candidates
_scanner._ordinary_baseline_probe_walks = _ordinary_baseline_probe_walks
