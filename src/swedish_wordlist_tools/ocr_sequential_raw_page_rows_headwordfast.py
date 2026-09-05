from __future__ import annotations

"""Fast headword-start experiment layered on the current correctness wrapper.

For page 1 row 0 we know that the first baseline-aligned headword glyph is a
bold variant of ``a``.  Try a diacritic-free bold ``a`` facit first.  The match
is deliberately asymmetric: every facit pixel must exist in the source, while
extra source pixels (notably a diacritic above the glyph) are allowed.

Placements are not swept blindly across a rectangle.  For each facit model we
first inspect source left-edge pixels in the headword-start area.  A source
left edge plus one of the facit's own left-edge pixels directly proposes
``(x0, baseline)``; only those placements get a full facit subset test.  Thus a
facit model is exhausted over all plausible positions before the next model is
tried.

If that stem match gives one unambiguous (text_start_x, baseline), walk the row
once.  Otherwise fall back unchanged to the current baseline-race wrapper.
"""

from . import ocr_sequential_raw_page_rows_homonymfix as _previous
from . import ocr_sequential_raw_page_rows as _scanner


_FALLBACK_PAGE1_BASELINE_PROBE_WALKS = _scanner._page1_baseline_probe_walks


def _source_left_edges(
    raw: set[tuple[int, int]],
    *,
    x_lo: int,
    x_hi: int,
    y_lo: int,
    y_hi: int,
) -> tuple[tuple[int, int], ...]:
    """Return black source pixels whose immediate left neighbour is white.

    These are cheap geometric anchors, not glyph decisions.  Separate accent
    components may also contribute edges; bad proposals simply fail the full
    facit subset check.
    """
    return tuple(
        sorted(
            (x, y)
            for x, y in raw
            if x_lo <= x <= x_hi
            and y_lo <= y <= y_hi
            and (x - 1, y) not in raw
        )
    )


def _page1_headword_subset_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    page_candidates = _scanner.cached._bound_page_candidates(models)
    stem_candidates = tuple(_scanner._bold_candidates(page_candidates, {"a"}))
    full_first_candidates = tuple(
        _scanner._bold_candidates(page_candidates, _scanner.PAGE1_EXACT_LABELS)
    )
    if not stem_candidates or not full_first_candidates:
        print("raw-page-headword-subset-probe: no bold a facit")
        return {}

    matches: dict[tuple[int, int], tuple] = {}
    proposals = 0
    full_tests = 0

    # Model outermost: completely try one facit glyph against source geometry
    # before moving on to another glyph model.
    for candidate in stem_candidates:
        model, min_x, left_pixels = candidate
        x0_lo = max(left, first_ink_x - _scanner.PAGE1_X_LEFT_SLACK)
        x0_hi = min(
            right - model.width,
            first_ink_x + _scanner.PAGE1_X_RIGHT_SLACK,
        )
        if x0_hi < x0_lo or not left_pixels:
            continue

        # A source anchor must line up with one of this model's known left-edge
        # pixels.  Include the model's vertical extent so accents or other ink
        # above the stem do not constrain the source window.
        source_edges = _source_left_edges(
            raw,
            x_lo=x0_lo + min_x,
            x_hi=x0_hi + min_x,
            y_lo=search_from + model.min_y,
            y_hi=(search_limit - 1) + model.max_y,
        )

        placements: set[tuple[int, int]] = set()
        for source_x, source_y in source_edges:
            for model_x, model_y in left_pixels:
                x0 = source_x - model_x
                baseline = source_y - model_y
                if x0 < x0_lo or x0 > x0_hi:
                    continue
                if baseline < search_from or baseline >= search_limit:
                    continue
                placements.add((x0, baseline))

        proposals += len(placements)
        for x0, baseline in sorted(placements):
            full_tests += 1
            placed = {
                (x0 + mx, baseline + py)
                for mx, py in model.pixels
            }
            # Intentionally one-way: every facit pixel must be present, but
            # extra source ink is allowed.  Plain ``a`` can therefore anchor
            # an accented variant without requiring the accent to be absent.
            if not placed or not placed.issubset(raw):
                continue
            text_start_x = x0 + min_x
            key = (text_start_x, baseline)
            old = matches.get(key)
            if old is None or len(model.pixels) > len(old[0].pixels):
                matches[key] = candidate

    print(
        "raw-page-headword-leftedge-probe: "
        f"models={len(stem_candidates)} proposals={proposals} full_tests={full_tests}"
    )

    if matches:
        diagnostics = ", ".join(
            f"x={text_x} b={baseline} label={candidate[0].label!r} "
            f"pixels={len(candidate[0].pixels)}"
            for (text_x, baseline), candidate in sorted(matches.items())
        )
        print(f"raw-page-headword-subset-probe: {diagnostics}")
    else:
        print("raw-page-headword-subset-probe: NONE")
        return {}

    if len(matches) != 1:
        print(
            "raw-page-headword-subset-fallback: "
            f"ambiguous_matches={len(matches)}"
        )
        return {}

    (text_start_x, baseline), _stem_candidate = next(iter(matches.items()))
    exact_first = _scanner._exact_first_candidates(
        raw,
        baseline,
        full_first_candidates,
        text_start_x,
        left,
        right,
    )
    if not exact_first:
        print(
            "raw-page-headword-subset-fallback: "
            f"stem matched at x={text_start_x} baseline={baseline} "
            "but ordinary first-candidate check failed"
        )
        return {}

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
        print(
            "raw-page-headword-subset-fallback: "
            f"x={text_start_x} baseline={baseline} row walk failed"
        )
        return {}

    score = (matched_right - text_start_x, glyphs, len(owned))
    print(
        "raw-page-headword-subset-win: "
        f"x={text_start_x} baseline={baseline} score={score}"
    )
    return {
        (text_start_x, baseline): (
            score,
            _stem_candidate[0],
            text_start_x - _stem_candidate[1],
            owned,
            glyphs,
            matched_right,
        )
    }


def _page1_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    walks = _page1_headword_subset_walks(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
        first_ink_x,
    )
    if walks:
        return walks
    return _FALLBACK_PAGE1_BASELINE_PROBE_WALKS(
        raw,
        search_from,
        search_limit,
        models,
        left,
        right,
        first_ink_x,
    )


_scanner._page1_baseline_probe_walks = _page1_baseline_probe_walks

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
