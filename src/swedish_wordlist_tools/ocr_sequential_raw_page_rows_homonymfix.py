from __future__ import annotations

"""Narrow homonym-placement correction for the sequential raw-page scanner.

Homonym digits use the row's already established support baseline. Their
vertical offset therefore remains entirely encoded in the facit model's
``pixels_relative_to_baseline``.

For diagnosis we explicitly try x placements around the true leftmost homonym
ink first: one pixel before it, exactly on it, and one pixel after it. The
previous wider x search remains as fallback, so this cannot remove an exact
match that used to be possible. If no exact match exists we print the best
same-baseline partial overlap, which tells us whether x anchoring or the facit
raster/y offset is the likely problem.

There is also one deliberately hard-coded diagnostic crop for page 1, column 1,
row 0: when the first raw-page read starts at y=170 in the left column, only
source pixels with 169 <= y <= 187 are exposed to the scanner. This is strictly
a temporary experiment to test whether the old-style tight vertical crop makes
the known homonym/headword row solvable again.
"""

from . import ocr_sequential_raw_page_rows as _scanner


_ORIGINAL_RAW_INK = _scanner._raw_ink


def _debug_cropped_raw_ink(
    context: dict,
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
) -> set[tuple[int, int]]:
    raw = _ORIGINAL_RAW_INK(
        context,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
    )

    # Deliberately hard-coded experiment: page 1, column 1, row 0.
    # Current raw layout for that column is x=50..246 and the scanner begins
    # row 0 at y=170 after the proven initial border y=169.
    if (
        context.get("raw_page_layout_source") == "page1-raw-pixels"
        and left == 50
        and right == 246
        and top == 170
    ):
        masked = {(x, y) for x, y in raw if 169 <= y <= 187}
        print(
            "raw-page-debug-crop: "
            f"column=1 row=0 y=169..187 raw_pixels={len(raw)} masked_pixels={len(masked)}"
        )
        return masked

    return raw


def _ordered_x0_candidates(
    raw: set[tuple[int, int]],
    *,
    left: int,
    probe_right: int,
    text_start_x: int,
    min_x: int,
):
    homonym_xs = [x for x, _y in raw if left <= x < text_start_x]
    first_ink_x = min(homonym_xs) if homonym_xs else None

    ordered: list[int] = []
    if first_ink_x is not None:
        for glyph_left_x in (first_ink_x - 1, first_ink_x, first_ink_x + 1):
            x0 = glyph_left_x - min_x
            if x0 not in ordered:
                ordered.append(x0)

    for x0 in range(left - min_x, probe_right - min_x):
        if x0 not in ordered:
            ordered.append(x0)
    return first_ink_x, ordered


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
    best_first_ink_x: int | None = None

    partial_model = None
    partial_x0: int | None = None
    partial_hits = -1
    partial_total = 0
    partial_first_ink_x: int | None = None

    for model, min_x, _left_pixels in page_candidates.homonym:
        first_ink_x, x0_candidates = _ordered_x0_candidates(
            raw,
            left=left,
            probe_right=probe_right,
            text_start_x=text_start_x,
            min_x=min_x,
        )
        for x0 in x0_candidates:
            placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
            if not placed:
                continue
            xs = [x for x, _y in placed]
            if min(xs) < left or min(xs) >= text_start_x:
                continue

            hits = len(placed & raw)
            if hits > partial_hits or (hits == partial_hits and len(placed) > partial_total):
                partial_model = model
                partial_x0 = x0
                partial_hits = hits
                partial_total = len(placed)
                partial_first_ink_x = first_ink_x

            if placed.issubset(raw) and len(placed) > len(best):
                best = placed
                best_model = model
                best_x0 = x0
                best_first_ink_x = first_ink_x

    if best and best_model is not None:
        ys = [y for _x, y in best]
        print(
            "raw-page-homonym: "
            f"label={best_model.label!r} model_id={getattr(best_model, 'model_id', None)!r} "
            f"baseline={baseline} model_y={best_model.min_y}..{best_model.max_y} "
            f"first_ink_x={best_first_ink_x} x0={best_x0} "
            f"pixels_y={min(ys)}..{max(ys)} pixels={len(best)}"
        )
    elif partial_model is not None:
        print(
            "raw-page-homonym-miss: "
            f"best_label={partial_model.label!r} "
            f"model_id={getattr(partial_model, 'model_id', None)!r} "
            f"baseline={baseline} model_y={partial_model.min_y}..{partial_model.max_y} "
            f"first_ink_x={partial_first_ink_x} x0={partial_x0} "
            f"overlap={partial_hits}/{partial_total}"
        )

    return best


_scanner._raw_ink = _debug_cropped_raw_ink
_scanner._match_homonym_on_baseline = _match_homonym_on_baseline

CachedRowBoundary = _scanner.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _scanner.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _scanner.START_SEARCH_HEIGHT
ensure_row_cached = _scanner.ensure_row_cached
cached_row = _scanner.cached_row
