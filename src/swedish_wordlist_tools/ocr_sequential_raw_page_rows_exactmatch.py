from __future__ import annotations

"""Require exact local glyph ink once a row baseline has been established.

The first glyph used while *discovering* a baseline may still use the deliberate
subset rule: every facit pixel must exist, while extra source ink is allowed.
That is what lets a diacritic-free stem prove the baseline of a diacritic glyph.

After that anchor, glyph recognition is strict.  Within the glyph's horizontal
black-pixel span and the typography's normal vertical extent around the chosen
baseline, source ink must equal the placed facit ink.  This prevents a too-small
facit (for example a bracket missing its last raster row) from being accepted
and then leaving that source pixel behind for the next text row.
"""

from . import ocr_sequential_raw_page_rows as _scanner
from . import ocr_sequential_raw_page_rows_headwordfast as _headwordfast
from . import ocr_sequential_raw_page_rows_homonymfix as _previous
from . import ocr_sequential_raw_page_rows_racesafe as _racesafe


def _vertical_extent(page_candidates) -> tuple[int, int]:
    lows: list[int] = []
    highs: list[int] = []
    for name in ("bold", "roman", "italic", "other", "homonym"):
        for model, _min_x, _left_pixels in getattr(page_candidates, name, ()):
            lows.append(int(model.min_y))
            highs.append(int(model.max_y))
    return min(lows, default=-12), max(highs, default=5)


def _placed_if_exact_local(model, x0: int, baseline: int, raw, page_candidates):
    """Return a placement only when local source ink equals the facit ink.

    Horizontal isolation is the model's actual black-pixel span.  The vertical
    window is shared by all candidate glyphs at this baseline, so disconnected
    diacritics and one-row protrusions are also visible to this check.
    """
    placed = _racesafe._placed_if_subset(model, x0, baseline, raw)
    if placed is None:
        return None

    x_lo = min(x for x, _y in placed)
    x_hi = max(x for x, _y in placed)
    rel_y_lo, rel_y_hi = _vertical_extent(page_candidates)
    y_lo = baseline + rel_y_lo
    y_hi = baseline + rel_y_hi

    for x in range(x_lo, x_hi + 1):
        for y in range(y_lo, y_hi + 1):
            point = (x, y)
            if point in raw and point not in placed:
                return None
    return placed


def _advance_one_exact(
    state: _previous._RaceState,
    page_candidates,
    *,
    left: int,
    right: int,
) -> bool:
    """Race step: subset for the anchor glyph, exact matching thereafter."""
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

            if state.matched_glyphs == 0:
                placed = _racesafe._placed_if_subset(
                    model, x0, state.baseline, state.remaining
                )
            else:
                placed = _placed_if_exact_local(
                    model, x0, state.baseline, state.remaining, page_candidates
                )
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
            _racesafe._remember_matched_glyph(state, model, placed, x0)
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


def _walk_baseline_exact(
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
    """Final row walk: baseline is known, therefore every glyph is exact."""
    page_candidates = _scanner.cached._bound_page_candidates(models)
    remaining = set(raw)
    owned: set[tuple[int, int]] = set()
    previous_style: str | None = None
    cursor = int(anchor_x)
    matched_glyphs = 0
    matched_right = cursor

    while cursor < right:
        if max_glyphs is not None and matched_glyphs >= max_glyphs:
            break
        if matched_glyphs == 0 and first_candidates is not None:
            candidates = first_candidates
        else:
            candidates = _scanner.cached._iter_candidates(
                page_candidates,
                first_glyph=matched_glyphs == 0,
                previous_style=previous_style,
                row_kind="unknown",
                leading_homonym_seen=False,
                baseline_established=True,
            )

        chosen = None
        for model, min_x, _left_pixels in candidates:
            x0 = cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = _placed_if_exact_local(
                model, x0, baseline, remaining, page_candidates
            )
            if placed is not None:
                chosen = (model, placed)
                break

        if chosen is not None:
            model, placed = chosen
            remaining.difference_update(placed)
            owned.update(placed)
            matched_glyphs += 1
            previous_style = _scanner.priority._typographic_style(model.style)
            glyph_right = max(px for px, _py in placed) + 1
            matched_right = max(matched_right, glyph_right)
            cursor = max(cursor + 1, glyph_right)
            continue

        later_x = [x for x, _y in remaining if x > cursor]
        if not later_x:
            break
        cursor = min(later_x)

    return matched_glyphs, owned, matched_right


# The conservative race resolves its module-global _advance_one at runtime.
# Keep the first anchor permissive there, but make all later race glyphs exact.
_racesafe._advance_one = _advance_one_exact
_previous._advance_one = _advance_one_exact

# Once _discover_row has selected a baseline it calls scanner._walk_baseline
# dynamically.  At that stage *including the first real glyph* must be exact.
_scanner._walk_baseline = _walk_baseline_exact
_previous._ORIGINAL_WALK_BASELINE = _walk_baseline_exact

# The single-row diagnostic wrapper delegates to this global after predicting
# the same glyph.  Point it at the strict implementation too.
_headwordfast._ORIGINAL_RACE_ADVANCE_ONE = _advance_one_exact

# Re-export the scanner surface expected by the debug/all-page runners.
_previous = _headwordfast._previous
_ORIGINAL_RACE_ADVANCE_ONE = _advance_one_exact
CachedRowBoundary = _headwordfast.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _headwordfast.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _headwordfast.START_SEARCH_HEIGHT
ensure_row_cached = _headwordfast.ensure_row_cached
cached_row = _headwordfast.cached_row
