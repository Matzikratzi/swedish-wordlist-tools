from __future__ import annotations

"""Hybrid correctness probe for the sequential raw-page scanner.

Baseline hypotheses now race incrementally from left to right.  Every candidate
keeps its own walker state; no candidate is restarted just because another
baseline is still alive.  The final full-row result is also cached so the main
scanner can reuse the proved walk instead of immediately walking the same row a
second time.

The leftmost ink may still be a superscript homonym and is therefore allowed to
propose baseline y without being the first baseline-aligned text glyph.
"""

from dataclasses import dataclass

from . import ocr_sequential_raw_page_rows as _scanner


_ORIGINAL_PAGE1_BASELINE_PROBE_WALKS = _scanner._page1_baseline_probe_walks
_ORIGINAL_WALK_BASELINE = _scanner._walk_baseline
_WALK_CACHE: dict[int, tuple[set[tuple[int, int]], dict[tuple, tuple]]] = {}


def _candidate_key(candidates) -> tuple | None:
    if candidates is None:
        return None
    return tuple((id(candidate[0]), int(candidate[1])) for candidate in candidates)


def _walk_key(
    baseline: int,
    left: int,
    right: int,
    anchor_x: int,
    first_candidates,
    max_glyphs: int | None,
) -> tuple:
    return (
        int(baseline),
        int(left),
        int(right),
        int(anchor_x),
        _candidate_key(first_candidates),
        max_glyphs,
    )


def _remember_walk(
    raw: set[tuple[int, int]],
    baseline: int,
    left: int,
    right: int,
    anchor_x: int,
    first_candidates,
    max_glyphs: int | None,
    result,
) -> None:
    raw_id = id(raw)
    entry = _WALK_CACHE.get(raw_id)
    if entry is None or entry[0] is not raw:
        entry = (raw, {})
        _WALK_CACHE[raw_id] = entry
    entry[1][
        _walk_key(
            baseline,
            left,
            right,
            anchor_x,
            first_candidates,
            max_glyphs,
        )
    ] = result


def _cached_walk_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
    *,
    first_candidates=None,
    max_glyphs: int | None = None,
):
    raw_id = id(raw)
    entry = _WALK_CACHE.get(raw_id)
    key = _walk_key(
        baseline,
        left,
        right,
        anchor_x,
        first_candidates,
        max_glyphs,
    )
    if entry is not None and entry[0] is raw and key in entry[1]:
        result = entry[1][key]
        print(
            "raw-page-walk-cache-hit: "
            f"x={anchor_x} baseline={baseline} glyphs={result[0]}"
        )
        return result

    result = _ORIGINAL_WALK_BASELINE(
        raw,
        baseline,
        models,
        left,
        right,
        anchor_x,
        first_candidates=first_candidates,
        max_glyphs=max_glyphs,
    )
    _remember_walk(
        raw,
        baseline,
        left,
        right,
        anchor_x,
        first_candidates,
        max_glyphs,
        result,
    )
    return result


@dataclass
class _RaceState:
    baseline: int
    cursor: int
    matched_right: int
    remaining: set[tuple[int, int]]
    first_candidates: tuple | list | None = None
    owned: set[tuple[int, int]] | None = None
    previous_style: str | None = None
    matched_glyphs: int = 0
    exhausted: bool = False

    def __post_init__(self) -> None:
        if self.owned is None:
            self.owned = set()


def _advance_one(
    state: _RaceState,
    page_candidates,
    *,
    left: int,
    right: int,
) -> bool:
    """Advance one candidate by exactly one matched glyph, never restarting it."""
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
        for model, min_x, _left_pixels in candidates:
            x0 = state.cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = {
                (x0 + mx, state.baseline + my)
                for mx, my in model.pixels
            }
            if placed and placed.issubset(state.remaining):
                chosen = (model, placed)
                break

        if chosen is not None:
            model, placed = chosen
            state.remaining.difference_update(placed)
            state.owned.update(placed)
            state.matched_glyphs += 1
            state.previous_style = _scanner.priority._typographic_style(model.style)
            glyph_right = max(px for px, _py in placed) + 1
            state.matched_right = max(state.matched_right, glyph_right)
            state.cursor = max(state.cursor + 1, glyph_right)
            return True

        later_x = [x for x, _y in state.remaining if x > state.cursor]
        if not later_x:
            state.exhausted = True
            return False
        state.cursor = min(later_x)

    state.exhausted = True
    return False


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
    """Walk all baseline candidates left-to-right in lockstep until exhausted.

    This is deliberately exact rather than heuristic: a candidate is discarded
    only when its walker has genuinely reached the end without another glyph.
    All final scores therefore remain comparable with the previous full-row
    implementation, but no candidate is ever restarted from the left.
    """
    page_candidates = _scanner.cached._bound_page_candidates(models)
    states: list[_RaceState] = []
    for baseline in sorted(set(int(b) for b in baselines)):
        first_candidates = None
        if first_candidates_by_baseline is not None:
            first_candidates = first_candidates_by_baseline.get(baseline)
            if not first_candidates:
                continue
        states.append(
            _RaceState(
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
            f"b={state.baseline}:glyphs={state.matched_glyphs}:right={state.matched_right}"
            for state in states
        )
    )

    results = {}
    for state in states:
        if state.matched_glyphs <= 0 or not state.owned:
            continue
        result = (
            state.matched_glyphs,
            set(state.owned),
            state.matched_right,
        )
        _remember_walk(
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


def _describe_homonym_models(page_candidates) -> None:
    models = []
    for model, min_x, left_pixels in page_candidates.homonym:
        models.append(
            f"label={model.label!r} id={getattr(model, 'model_id', None)!r} "
            f"pixels={len(model.pixels)} x={min_x}..{min_x + model.width - 1} "
            f"y={model.min_y}..{model.max_y} left_pixels={len(left_pixels)}"
        )
    print(
        "raw-page-homonym-models: "
        + ("; ".join(models) if models else "NONE")
    )


def _homonym_baseline_seeds(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
) -> dict[int, set[tuple[int, int]]]:
    """Return exact homonym-derived baseline candidates and their proved pixels."""
    page_candidates = _scanner.cached._bound_page_candidates(models)
    _describe_homonym_models(page_candidates)
    probe_right = min(right, left + _scanner.HOMONYM_PROBE_WIDTH)
    anchor_bottom = min(search_limit, search_from + _scanner.START_SEARCH_HEIGHT)
    seeds: dict[int, set[tuple[int, int]]] = {}

    for anchor_y in range(search_from, anchor_bottom):
        xs = sorted(x for x, y in raw if y == anchor_y and left <= x < probe_right)
        for anchor_x in xs:
            for model, min_x, left_pixels in page_candidates.homonym:
                x0 = anchor_x - min_x
                if x0 < left or x0 + model.width > probe_right:
                    continue
                for _mx, my in left_pixels:
                    baseline = anchor_y - my
                    if baseline < search_from or baseline >= search_limit:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if not placed or not placed.issubset(raw):
                        continue
                    print(
                        "raw-page-homonym-exact: "
                        f"label={model.label!r} id={getattr(model, 'model_id', None)!r} "
                        f"anchor=({anchor_x},{anchor_y}) x0={x0} baseline={baseline} "
                        f"pixels={len(placed)}"
                    )
                    old = seeds.get(baseline)
                    if old is None or len(placed) > len(old):
                        seeds[baseline] = placed

    return seeds


def _local_xfirst_baseline_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
):
    """Generate baseline y at the true x-first ink, then race left-to-right."""
    anchor_x = _scanner._x_first_ink_x(
        raw,
        search_from=search_from,
        search_limit=search_limit,
        left=left,
        right=right,
        include_homonym=True,
    )
    if anchor_x is None:
        return {}

    page_candidates = _scanner.cached._bound_page_candidates(models)
    anchor_bottom = min(search_limit, search_from + _scanner.START_SEARCH_HEIGHT)
    hypotheses: set[int] = set()

    for anchor_y in range(search_from, anchor_bottom):
        if (anchor_x, anchor_y) not in raw:
            continue
        for model, min_x, left_pixels in _scanner.cached._iter_candidates(
            page_candidates,
            first_glyph=True,
            previous_style=None,
            row_kind="unknown",
            leading_homonym_seen=False,
            baseline_established=False,
        ):
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

    raced = _race_baselines(
        raw,
        hypotheses,
        models,
        left,
        right,
        anchor_x,
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
        print(
            f"raw-page-local-xfirst-baseline-candidates: x={anchor_x} "
            f"{diagnostics}"
        )
    else:
        print(f"raw-page-local-xfirst-baseline-candidates: x={anchor_x} NONE")
    return walks


def _page1_text_walks_on_proved_baselines(
    raw: set[tuple[int, int]],
    local_walks,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    """Locate the real first headword glyph after x-first proves baseline y."""
    page_candidates = _scanner.cached._bound_page_candidates(models)
    first_candidates = tuple(
        _scanner._bold_candidates(page_candidates, _scanner.PAGE1_EXACT_LABELS)
    )
    walks = {}

    best_local_score = max(item[0] for item in local_walks.values())
    proved_baselines = sorted(
        baseline
        for (_probe_x, baseline), item in local_walks.items()
        if item[0] == best_local_score
    )

    for baseline in proved_baselines:
        for candidate in first_candidates:
            model, min_x, _left_pixels = candidate
            x0_lo = max(left, first_ink_x - _scanner.PAGE1_X_LEFT_SLACK)
            x0_hi = min(
                right - model.width,
                first_ink_x + _scanner.PAGE1_X_RIGHT_SLACK,
            )
            if x0_hi < x0_lo:
                continue
            for x0 in range(x0_lo, x0_hi + 1):
                placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                if not placed or not placed.issubset(raw):
                    continue
                text_start_x = x0 + min_x
                exact_first = _scanner._exact_first_candidates(
                    raw,
                    baseline,
                    first_candidates,
                    text_start_x,
                    left,
                    right,
                )
                if not exact_first:
                    continue
                glyphs, owned, matched_right = _scanner._walk_baseline(
                    raw,
                    baseline,
                    models,
                    left,
                    right,
                    text_start_x,
                    first_candidates=exact_first,
                )
                if glyphs <= 0 or not owned:
                    continue
                score = (matched_right - text_start_x, glyphs, len(owned))
                key = (text_start_x, baseline)
                value = (
                    score,
                    model,
                    x0,
                    owned,
                    glyphs,
                    matched_right,
                )
                old = walks.get(key)
                if old is None or score > old[0]:
                    walks[key] = value

    if walks:
        diagnostics = ", ".join(
            f"x={text_x} b={baseline}:score={item[0]}"
            for (text_x, baseline), item in sorted(walks.items())
        )
        print(f"raw-page-local-xfirst-text-candidates: {diagnostics}")
    return walks


def _page1_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    """Use leftmost ink to prove baseline y, then find a real headword glyph x."""
    local_walks = _local_xfirst_baseline_walks(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
    )
    if local_walks:
        text_walks = _page1_text_walks_on_proved_baselines(
            raw,
            local_walks,
            models,
            left,
            right,
            first_ink_x,
        )
        if text_walks:
            probe_x = next(iter(local_walks))[0]
            text_xs = sorted({text_x for text_x, _baseline in text_walks})
            print(
                "raw-page-local-xfirst-baseline-handoff: "
                f"probe_x={probe_x} exact_text_x={text_xs}"
            )
            return text_walks
        print(
            "raw-page-local-xfirst-baseline-handoff: "
            f"probe_x={next(iter(local_walks))[0]} no exact headword glyph"
        )

    page_candidates = _scanner.cached._bound_page_candidates(models)
    first_candidates = tuple(
        _scanner._bold_candidates(page_candidates, _scanner.PAGE1_EXACT_LABELS)
    )
    seeds = _homonym_baseline_seeds(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
    )

    walks = {}
    for baseline, homonym_owned in sorted(seeds.items()):
        exact_first = _scanner._exact_first_candidates(
            raw,
            baseline,
            first_candidates,
            first_ink_x,
            left,
            right,
        )
        if not exact_first:
            continue
        glyphs, owned, matched_right = _scanner._walk_baseline(
            raw,
            baseline,
            models,
            left,
            right,
            first_ink_x,
            first_candidates=exact_first,
        )
        if glyphs <= 0 or not owned:
            continue
        total_owned = set(owned)
        total_owned.update(homonym_owned)
        score = (matched_right - first_ink_x, glyphs + 1, len(total_owned))
        walks[(first_ink_x, baseline)] = (
            score,
            None,
            first_ink_x,
            total_owned,
            glyphs + 1,
            matched_right,
        )

    if walks:
        baselines = ",".join(str(b) for _x, b in sorted(walks))
        print(f"raw-page-homonym-baseline-seed: baselines={baselines}")
        return walks

    print("raw-page-homonym-baseline-seed: no exact seed; using ordinary page1 probe")
    return _ORIGINAL_PAGE1_BASELINE_PROBE_WALKS(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
        first_ink_x,
    )


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
    """Generate exact baseline hypotheses, then race them left-to-right."""
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


_scanner._walk_baseline = _cached_walk_baseline
_scanner._page1_baseline_probe_walks = _page1_baseline_probe_walks
_scanner._ordinary_baseline_probe_walks = _ordinary_baseline_probe_walks

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
