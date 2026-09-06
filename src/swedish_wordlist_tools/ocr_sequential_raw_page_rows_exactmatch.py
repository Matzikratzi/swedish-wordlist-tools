from __future__ import annotations

"""Choose the most specific facit match once a row baseline is established.

The first glyph used while *discovering* a baseline may still use the deliberate
subset rule: every facit pixel must exist, while extra source ink is allowed.
That lets a diacritic-free stem prove the baseline of a diacritic glyph.

After the baseline is known, however, accepting the first subset candidate is
wrong: ``o`` is a subset of ``ö``, ``L`` can be a subset of ``b``, and a small
punctuation/bracket model can leave real glyph pixels behind.  A rectangular
"no extra ink" check was also wrong because neighbouring printed glyphs may
touch or enter the same x span.

Instead, at each fixed (cursor, baseline), enumerate every facit placement that
is a subset of the remaining source ink and choose the most specific placement:
first the one with most facit pixels, then the one with the wider black-pixel
span.  Candidate order remains the final tie breaker.  This keeps neighbouring
ink legal while preventing a smaller facit from winning merely because it was
encountered first.
"""

from . import ocr_sequential_raw_page_rows as _scanner
from . import ocr_sequential_raw_page_rows_headwordfast as _headwordfast
from . import ocr_sequential_raw_page_rows_homonymfix as _previous
from . import ocr_sequential_raw_page_rows_racesafe as _racesafe


def _best_subset_candidate(candidates, *, cursor: int, baseline: int, raw, left: int, right: int):
    """Return the largest compatible facit placement at one cursor/baseline.

    All candidates must contain only source pixels.  Extra source pixels are
    intentionally ignored here: they may belong to a diacritic model that will
    win by size, or to a touching neighbouring glyph.  Therefore maximal facit
    support is a safer discriminator than an isolation rectangle.
    """
    best = None
    best_score = None
    for order, (model, min_x, _left_pixels) in enumerate(candidates):
        x0 = cursor - min_x
        if x0 < left or x0 + model.width > right:
            continue
        placed = _racesafe._placed_if_subset(model, x0, baseline, raw)
        if placed is None:
            continue
        x_lo = min(x for x, _y in placed)
        x_hi = max(x for x, _y in placed)
        score = (len(placed), x_hi - x_lo + 1, -order)
        if best_score is None or score > best_score:
            best_score = score
            best = (model, placed, x0)
    return best


def _advance_one_maximal(
    state: _previous._RaceState,
    page_candidates,
    *,
    left: int,
    right: int,
) -> bool:
    """Race step: permissive first anchor, maximal facit matches thereafter."""
    while state.cursor < right:
        if state.matched_glyphs == 0 and state.first_candidates is not None:
            candidates = state.first_candidates
        else:
            candidates = tuple(
                _scanner.cached._iter_candidates(
                    page_candidates,
                    first_glyph=state.matched_glyphs == 0,
                    previous_style=state.previous_style,
                    row_kind="unknown",
                    leading_homonym_seen=False,
                    baseline_established=True,
                )
            )

        if state.matched_glyphs == 0:
            # Baseline discovery deliberately keeps its asymmetric anchor rule
            # and existing candidate priority.  This match is evidence for the
            # baseline, not yet the final glyph identity.
            chosen = None
            for model, min_x, _left_pixels in candidates:
                x0 = state.cursor - min_x
                if x0 < left or x0 + model.width > right:
                    continue
                placed = _racesafe._placed_if_subset(
                    model, x0, state.baseline, state.remaining
                )
                if placed is not None:
                    chosen = (model, placed, x0)
                    break
        else:
            chosen = _best_subset_candidate(
                candidates,
                cursor=state.cursor,
                baseline=state.baseline,
                raw=state.remaining,
                left=left,
                right=right,
            )

        blocked_small = None
        if chosen is not None:
            model, placed, x0 = chosen
            is_small = len(placed) <= _previous._SMALL_GLYPH_MAX_PIXELS
            if (
                not state.baseline_verified
                and is_small
                and state.leading_small_glyphs >= _previous._MAX_LEADING_SMALL_GLYPHS
            ):
                blocked_small = chosen
                chosen = None

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


def _walk_baseline_maximal(
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
    """Final row walk: choose the largest compatible facit at every glyph."""
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
            candidates = tuple(first_candidates)
        else:
            candidates = tuple(
                _scanner.cached._iter_candidates(
                    page_candidates,
                    first_glyph=matched_glyphs == 0,
                    previous_style=previous_style,
                    row_kind="unknown",
                    leading_homonym_seen=False,
                    baseline_established=True,
                )
            )

        chosen = _best_subset_candidate(
            candidates,
            cursor=cursor,
            baseline=baseline,
            raw=remaining,
            left=left,
            right=right,
        )

        if chosen is not None:
            model, placed, _x0 = chosen
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
# Keep the first anchor permissive there, but use maximal matches afterwards.
_racesafe._advance_one = _advance_one_maximal
_previous._advance_one = _advance_one_maximal

# Once _discover_row has selected a baseline it calls scanner._walk_baseline
# dynamically.  At that stage even the first real glyph gets maximal matching.
_scanner._walk_baseline = _walk_baseline_maximal
_previous._ORIGINAL_WALK_BASELINE = _walk_baseline_maximal

# The single-row diagnostic wrapper delegates to this global after predicting
# the same glyph.  Point it at the maximal implementation too.
_headwordfast._ORIGINAL_RACE_ADVANCE_ONE = _advance_one_maximal

# Re-export the scanner surface expected by the debug/all-page runners.
_previous = _headwordfast._previous
_ORIGINAL_RACE_ADVANCE_ONE = _advance_one_maximal
CachedRowBoundary = _headwordfast.CachedRowBoundary
FIRST_TEXT_SEARCH_WIDTH = _headwordfast.FIRST_TEXT_SEARCH_WIDTH
START_SEARCH_HEIGHT = _headwordfast.START_SEARCH_HEIGHT
ensure_row_cached = _headwordfast.ensure_row_cached
cached_row = _headwordfast.cached_row
