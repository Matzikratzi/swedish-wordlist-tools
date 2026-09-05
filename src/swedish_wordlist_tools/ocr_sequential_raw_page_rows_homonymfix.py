from __future__ import annotations

"""Narrow homonym-placement correction for the sequential raw-page scanner.

Homonym digits use the row's already established support baseline.  Their
vertical offset therefore remains entirely encoded in the facit model's
``pixels_relative_to_baseline``.  The only correction here is geometric in x:
a raised homonym may occupy an x column also occupied by the following
headword at another y, so it must not be rejected merely because its rightmost
x reaches/passes the headword's first-ink x.

Kept as a tiny wrapper while the raw-page geometry is being validated so this
change is easy to test independently.
"""

from . import ocr_sequential_raw_page_rows as _scanner


def _match_homonym_on_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    text_start_x: int,
) -> set[tuple[int, int]]:
    page_candidates = _scanner.cached._bound_page_candidates(models)
    probe_right = min(text_start_x, left + _scanner.HOMONYM_PROBE_WIDTH)
    if probe_right <= left:
        return set()

    best: set[tuple[int, int]] = set()
    best_model = None
    best_x0: int | None = None

    for model, min_x, _left_pixels in page_candidates.homonym:
        # The model's left edge must still begin in the homonym start strip.
        # Its right edge may however share x columns with the headword: the two
        # glyphs are vertically separated, so x overlap alone is not a reason
        # to reject an otherwise exact raster match.
        for x0 in range(left - min_x, probe_right - min_x):
            placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
            if not placed:
                continue
            xs = [x for x, _y in placed]
            if min(xs) < left or min(xs) >= text_start_x:
                continue
            if placed.issubset(raw) and len(placed) > len(best):
                best = placed
                best_model = model
                best_x0 = x0

    if best and best_model is not None:
        ys = [y for _x, y in best]
        print(
            "raw-page-homonym: "
            f"label={best_model.label!r} model_id={getattr(best_model, 'model_id', None)!r} "
            f"baseline={baseline} model_y={best_model.min_y}..{best_model.max_y} "
            f"x0={best_x0} pixels_y={min(ys)}..{max(ys)} pixels={len(best)}"
        )

    return best


_scanner._match_homonym_on_baseline = _match_homonym_on_baseline

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
