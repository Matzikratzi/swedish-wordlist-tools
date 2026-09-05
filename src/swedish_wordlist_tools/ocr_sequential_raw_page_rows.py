from __future__ import annotations

"""Sequential baseline discovery with cached row boundaries.

Each row has three vertical limits:
- row_top: stable start of the row work area,
- provisional_bottom: temporary generous search limit while solving the row,
- final_bottom: tightened to the lowest pixel proven by the completed row walk.

Only final_bottom is used to advance to the next row. Legacy per-row bottoms are
never used as OCR limits.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from .ocr_raw_page_baseline_row import _raw_ink


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    row_top: int
    provisional_bottom: int
    baseline: int
    final_bottom: int
    next_search_y: int
    matched_glyphs: int
    matched_pixels: int
    matched_right: int


def _cache(context: dict) -> dict[int, list[CachedRowBoundary]]:
    return context.setdefault("raw_page_row_boundary_cache", {})


def _column_bounds(context: dict, column: int) -> tuple[int, int, int, int]:
    entry = context["row_map"]["columns"][column]
    owners = context["pixel_owners"]
    left = int(entry.get("crop_left", entry.get("left", 0)))
    right = int(entry.get("crop_right", entry.get("right", owners.width)))
    rows = entry.get("rows") or []
    top = max(0, min((int(r["page_top"]) for r in rows), default=0) - 12)
    bottom = min(owners.height, max((int(r["page_bottom"]) for r in rows), default=owners.height) + 12)
    return left, top, right, bottom


def _provisional_height(models) -> int:
    """Generous work height derived from glyph models, not row geometry."""
    heights = [int(getattr(model, "height", 0) or 0) for model in models]
    tallest = max(heights, default=16)
    return max(24, tallest + 12)


def _walk_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
) -> tuple[int, set[tuple[int, int]], int]:
    """Consume one row left-to-right on a fixed baseline.

    Pixels from neighbouring rows may be present in the provisional work area,
    but they cannot be consumed unless a complete glyph model fits them on this
    exact baseline. Gaps are allowed: they move the cursor, not the baseline.
    """
    page_candidates = cached._bound_page_candidates(models)
    remaining = set(raw)
    owned: set[tuple[int, int]] = set()
    previous_style: str | None = None
    cursor = int(anchor_x)
    matched_glyphs = 0
    matched_right = cursor

    while cursor < right:
        chosen = None
        for model, min_x, _left_pixels in cached._iter_candidates(
            page_candidates,
            first_glyph=matched_glyphs == 0,
            previous_style=previous_style,
            row_kind="unknown",
            leading_homonym_seen=False,
            baseline_established=True,
        ):
            x0 = cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = {(x0 + mx, baseline + my) for mx, my in model.pixels}
            if placed and placed.issubset(remaining):
                chosen = (model, x0, placed)
                break

        if chosen is not None:
            model, x0, placed = chosen
            remaining.difference_update(placed)
            owned.update(placed)
            matched_glyphs += 1
            previous_style = priority._typographic_style(model.style)
            glyph_right = max(px for px, _py in placed) + 1
            matched_right = max(matched_right, glyph_right)
            cursor = max(cursor + 1, glyph_right)
            continue

        # Whitespace or a pixel belonging to another row: advance horizontally.
        # We deliberately do not jump to an arbitrary lower pixel and therefore
        # cannot create a new baseline while this row is being solved.
        later_x = [x for x, _y in remaining if x > cursor]
        if not later_x:
            break
        cursor = min(later_x)

    return matched_glyphs, owned, matched_right


def _discover_next(context: dict, column: int, row_index: int, row_top: int, models) -> CachedRowBoundary:
    left, column_top, right, column_bottom = _column_bounds(context, column)
    row_top = max(column_top, int(row_top))
    provisional_bottom = min(column_bottom, row_top + _provisional_height(models))
    raw = _raw_ink(context, left=left, right=right, top=row_top, bottom=provisional_bottom)
    page_candidates = cached._bound_page_candidates(models)

    # A new row can only be proposed from ink close to the lexical left edge.
    # Once proposed, the complete row is walked before its bottom is tightened.
    start_slack = 40
    for anchor_y in range(row_top, provisional_bottom):
        xs = sorted(x for x, y in raw if y == anchor_y and x <= left + start_slack)
        for anchor_x in xs:
            hypotheses: set[int] = set()
            for model, min_x, left_pixels in cached._iter_candidates(
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
                    if baseline < row_top or baseline >= provisional_bottom:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if placed and placed.issubset(raw):
                        hypotheses.add(baseline)
            if not hypotheses:
                continue

            walks = []
            for baseline in sorted(hypotheses):
                glyphs, owned, matched_right = _walk_baseline(
                    raw, baseline, models, left, right, anchor_x
                )
                # Prefer the hypothesis that explains a coherent row furthest
                # to the right, then the most glyphs/pixels. The first glyph is
                # not enough by itself to establish the baseline.
                score = (matched_right, glyphs, len(owned))
                walks.append((score, baseline, owned, glyphs, matched_right))

            best_score = max(score for score, _baseline, _owned, _glyphs, _right in walks)
            best = [item for item in walks if item[0] == best_score and item[3] > 0]
            if len(best) != 1:
                continue

            _score, baseline, owned, glyphs, matched_right = best[0]
            # Tighten only after the row walker has finished. This is exactly
            # one pixel below the lowest pixel proven to belong to this row.
            final_bottom = max(y for _x, y in owned) + 1
            return CachedRowBoundary(
                row=row_index,
                row_top=row_top,
                provisional_bottom=provisional_bottom,
                baseline=baseline,
                final_bottom=final_bottom,
                next_search_y=final_bottom,
                matched_glyphs=glyphs,
                matched_pixels=len(owned),
                matched_right=matched_right,
            )

    raise RuntimeError(
        f"sequential raw-page discovery stopped at column={column} row={row_index}: "
        f"no unique walked baseline in work area y={row_top}..{provisional_bottom}"
    )


def ensure_row_cached(context: dict, column: int, target_row: int, models) -> list[CachedRowBoundary]:
    if target_row < 0:
        raise ValueError("target_row must be >= 0")
    cache = _cache(context).setdefault(column, [])
    _left, column_top, _right, _bottom = _column_bounds(context, column)
    while len(cache) <= target_row:
        row_index = len(cache)
        row_top = column_top if not cache else cache[-1].final_bottom
        cache.append(_discover_next(context, column, row_index, row_top, models))
    return cache


def cached_row(context: dict, column: int, row: int, models) -> CachedRowBoundary:
    return ensure_row_cached(context, column, row, models)[row]
