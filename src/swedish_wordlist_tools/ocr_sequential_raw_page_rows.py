from __future__ import annotations

"""Sequential baseline discovery with cached row boundaries.

Each row has three vertical limits:
- row_top: stable start of the row work area,
- provisional_bottom: temporary generous search limit while solving the row,
- final_bottom: tightened to the lowest pixel proven by matched glyph models.

Only final_bottom is used to advance to the next row. Legacy per-row bottoms are
never used as OCR limits.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from .ocr_raw_page_baseline_row import _raw_ink


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    row_top: int
    provisional_bottom: int
    baseline: int
    final_bottom: int
    next_search_y: int


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
    # Enough room for ascenders/descenders plus whitespace while still keeping
    # the working raster local. It is temporary and carries no ownership.
    return max(24, tallest + 12)


def _baseline_score(raw: set[tuple[int, int]], baseline: int, models, left: int, right: int) -> tuple[int, int | None]:
    """Count complete glyph placements explained by pixels on one baseline."""
    page_candidates = cached._bound_page_candidates(models)
    count = 0
    bottom = None
    for x in sorted({x for x, _y in raw}):
        for model, min_x, _left_pixels in cached._iter_candidates(
            page_candidates, first_glyph=False, previous_style=None,
            row_kind="unknown", leading_homonym_seen=False,
            baseline_established=True,
        ):
            x0 = x - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = {(x0 + mx, baseline + my) for mx, my in model.pixels}
            if placed and placed.issubset(raw):
                count += 1
                model_bottom = max(py for _px, py in placed) + 1
                bottom = model_bottom if bottom is None else max(bottom, model_bottom)
                break
    return count, bottom


def _discover_next(context: dict, column: int, row_index: int, row_top: int, models) -> CachedRowBoundary:
    left, column_top, right, column_bottom = _column_bounds(context, column)
    row_top = max(column_top, int(row_top))
    provisional_bottom = min(column_bottom, row_top + _provisional_height(models))
    raw = _raw_ink(context, left=left, right=right, top=row_top, bottom=provisional_bottom)
    page_candidates = cached._bound_page_candidates(models)

    # A new row can only be established from ink close to a lexical left start.
    # The provisional bottom merely limits the work area; it is not a boundary.
    start_slack = 40
    for anchor_y in range(row_top, provisional_bottom):
        xs = sorted(x for x, y in raw if y == anchor_y and x <= left + start_slack)
        for anchor_x in xs:
            hypotheses: set[int] = set()
            for model, min_x, left_pixels in cached._iter_candidates(
                page_candidates, first_glyph=True, previous_style=None,
                row_kind="unknown", leading_homonym_seen=False,
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

            scored = []
            for baseline in sorted(hypotheses):
                score, proven_bottom = _baseline_score(raw, baseline, models, left, right)
                scored.append((score, baseline, proven_bottom))
            best_score = max(score for score, _baseline, _bottom in scored)
            best = [(baseline, proven_bottom) for score, baseline, proven_bottom in scored if score == best_score]
            if best_score > 0 and len(best) == 1:
                baseline, proven_bottom = best[0]
                # Tighten aggressively when the row is done: final_bottom is
                # exactly one pixel below the lowest proven glyph pixel.
                final_bottom = max(baseline + 1, int(proven_bottom or (baseline + 1)))
                return CachedRowBoundary(
                    row=row_index,
                    row_top=row_top,
                    provisional_bottom=provisional_bottom,
                    baseline=baseline,
                    final_bottom=final_bottom,
                    next_search_y=final_bottom,
                )

    raise RuntimeError(
        f"sequential raw-page discovery stopped at column={column} row={row_index}: "
        f"no unique baseline in work area y={row_top}..{provisional_bottom}"
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
