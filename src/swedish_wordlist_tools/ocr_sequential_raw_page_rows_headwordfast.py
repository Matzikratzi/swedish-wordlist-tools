from __future__ import annotations

"""Fast headword-start experiment layered on the current correctness wrapper.

For page 1 row 0 we know that the first baseline-aligned headword glyph is a
bold variant of ``a``. Try a diacritic-free bold ``a`` facit first. The match
is deliberately asymmetric: every facit pixel must exist in the source, while
extra source pixels (notably a diacritic above the glyph) are allowed.

Placements are not swept blindly across a rectangle. For each facit model we
first inspect source left-edge pixels in the headword-start area. A source
left edge plus one of the facit's own left-edge pixels directly proposes
``(x0, baseline)``; only those placements get a full facit subset test.
"""

from . import ocr_sequential_raw_page_rows_homonymfix as _previous
from . import ocr_sequential_raw_page_rows as _scanner


_FALLBACK_PAGE1_BASELINE_PROBE_WALKS = _scanner._page1_baseline_probe_walks
_ORIGINAL_RACE_ADVANCE_ONE = _previous._advance_one


def _trace_race_advance_one(state, page_candidates, *, left: int, right: int) -> bool:
    """Show exactly which facit glyph keeps each baseline candidate alive."""
    before_n = state.matched_glyphs
    before_cursor = state.cursor

    # Predict the exact candidate the underlying walker will choose at its
    # current cursor.  This duplicates only the chooser so diagnostics can name
    # the model; the real state transition is still performed by the original.
    cursor = state.cursor
    remaining = state.remaining
    predicted = None
    while cursor < right:
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
        for model, min_x, _left_pixels in candidates:
            x0 = cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = {(x0 + mx, state.baseline + my) for mx, my in model.pixels}
            if placed and placed.issubset(remaining):
                predicted = (cursor, x0, model, len(placed))
                break
        if predicted is not None:
            break
        later_x = [x for x, _y in remaining if x > cursor]
        if not later_x:
            break
        cursor = min(later_x)

    advanced = _ORIGINAL_RACE_ADVANCE_ONE(state, page_candidates, left=left, right=right)
    if advanced and state.matched_glyphs == before_n + 1:
        if predicted is None:
            print(
                "raw-page-race-glyph: "
                f"b={state.baseline} n={state.matched_glyphs} from_x={before_cursor} UNKNOWN"
            )
        else:
            match_x, x0, model, pixels = predicted
            print(
                "raw-page-race-glyph: "
                f"b={state.baseline} n={state.matched_glyphs} x={match_x} x0={x0} "
                f"label={model.label!r} id={getattr(model, 'model_id', None)!r} "
                f"style={getattr(model, 'style', None)!r} pixels={pixels}"
            )
    return advanced


# Diagnostic only: _race_baselines resolves _advance_one in the previous
# module at runtime, so replacing it here exposes every glyph chosen by the
# existing race without changing its decisions.
_previous._advance_one = _trace_race_advance_one


def _source_left_edges(raw, *, x_lo, x_hi, y_lo, y_hi):
    return tuple(sorted((x, y) for x, y in raw if x_lo <= x <= x_hi and y_lo <= y <= y_hi and (x - 1, y) not in raw))


def _page1_headword_subset_walks(raw, search_from, search_limit, models, left, right, first_ink_x):
    page_candidates = _scanner.cached._bound_page_candidates(models)
    stem_candidates = tuple(_scanner._bold_candidates(page_candidates, {"a"}))
    full_first_candidates = tuple(_scanner._bold_candidates(page_candidates, _scanner.PAGE1_EXACT_LABELS))
    if not stem_candidates or not full_first_candidates:
        print("raw-page-headword-subset-probe: no bold a facit")
        return {}

    matches = {}
    proposals = 0
    full_tests = 0
    for candidate in stem_candidates:
        model, min_x, left_pixels = candidate
        x0_lo = max(left, first_ink_x - _scanner.PAGE1_X_LEFT_SLACK)
        x0_hi = min(right - model.width, first_ink_x + _scanner.PAGE1_X_RIGHT_SLACK)
        if x0_hi < x0_lo or not left_pixels:
            continue
        source_edges = _source_left_edges(
            raw,
            x_lo=x0_lo + min_x,
            x_hi=x0_hi + min_x,
            y_lo=search_from + model.min_y,
            y_hi=(search_limit - 1) + model.max_y,
        )
        placements = set()
        for source_x, source_y in source_edges:
            for model_x, model_y in left_pixels:
                x0 = source_x - model_x
                baseline = source_y - model_y
                if x0_lo <= x0 <= x0_hi and search_from <= baseline < search_limit:
                    placements.add((x0, baseline))
        proposals += len(placements)
        for x0, baseline in sorted(placements):
            full_tests += 1
            placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
            if not placed or not placed.issubset(raw):
                continue
            text_start_x = x0 + min_x
            key = (text_start_x, baseline)
            old = matches.get(key)
            if old is None or len(model.pixels) > len(old[0].pixels):
                matches[key] = candidate

    print(f"raw-page-headword-leftedge-probe: models={len(stem_candidates)} proposals={proposals} full_tests={full_tests}")
    if matches:
        diagnostics = ", ".join(
            f"x={text_x} b={baseline} label={candidate[0].label!r} pixels={len(candidate[0].pixels)}"
            for (text_x, baseline), candidate in sorted(matches.items())
        )
        print(f"raw-page-headword-subset-probe: {diagnostics}")
    else:
        print("raw-page-headword-subset-probe: NONE")
        return {}
    if len(matches) != 1:
        print(f"raw-page-headword-subset-fallback: ambiguous_matches={len(matches)}")
        return {}

    (text_start_x, baseline), stem_candidate = next(iter(matches.items()))
    exact_first = _scanner._exact_first_candidates(raw, baseline, full_first_candidates, text_start_x, left, right)
    if not exact_first:
        print(f"raw-page-headword-subset-fallback: stem matched at x={text_start_x} baseline={baseline} but ordinary first-candidate check failed")
        return {}
    glyphs, owned, matched_right = _scanner._walk_baseline(raw, baseline, models, left, right, text_start_x, first_candidates=exact_first)
    if glyphs <= 0 or not owned:
        print(f"raw-page-headword-subset-fallback: x={text_start_x} baseline={baseline} row walk failed")
        return {}
    score = (matched_right - text_start_x, glyphs, len(owned))
    print(f"raw-page-headword-subset-win: x={text_start_x} baseline={baseline} score={score}")
    return {(text_start_x, baseline): (score, stem_candidate[0], text_start_x - stem_candidate[1], owned, glyphs, matched_right)}


def _page1_baseline_probe_walks(raw, search_from, search_limit, models, left, right, first_ink_x):
    walks = _page1_headword_subset_walks(raw, search_from, search_limit, models, left, right, first_ink_x)
    if walks:
        return walks
    return _FALLBACK_PAGE1_BASELINE_PROBE_WALKS(raw, search_from, search_limit, models, left, right, first_ink_x)


_scanner._page1_baseline_probe_walks = _page1_baseline_probe_walks

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
