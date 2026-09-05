from __future__ import annotations

"""Sequential baseline discovery with cached row boundaries.

Rows are discovered from the top of a column. Legacy row top/bottom values are
not used to jump to a requested row. Several baseline hypotheses may survive
the first glyph; they are scored by how many complete glyph models they can
explain on that baseline before a baseline is cached.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from .ocr_raw_page_baseline_row import _raw_ink


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    baseline: int
    content_bottom: int | None
    next_search_y: int


def _cache(context: dict) -> dict[int, list[CachedRowBoundary]]:
    return context.setdefault("raw_page_row_boundary_cache", {})


def _column_bounds(context: dict, column: int) -> tuple[int, int, int, int]:
    entry = context["row_map"]["columns"][column]
    owners = context["pixel_owners"]
    left = int(entry.get("crop_left", entry.get("left", 0)))
    right = int(entry.get("crop_right", entry.get("right", owners.width)))
    rows = entry.get("rows") or []
    # Column top/bottom are page/column geometry, not per-row boundaries.
    top = max(0, min((int(r["page_top"]) for r in rows), default=0) - 12)
    bottom = min(owners.height, max((int(r["page_bottom"]) for r in rows), default=owners.height) + 12)
    return left, top, right, bottom


def _baseline_score(raw: set[tuple[int, int]], baseline: int, models, left: int, right: int) -> tuple[int, int | None]:
    """Count model placements explained by raw pixels on one baseline."""
    page_candidates = cached._bound_page_candidates(models)
    count = 0
    bottom = None
    # Score complete glyphs anywhere on this baseline. This is only used to
    # disambiguate baseline hypotheses; actual row text decoding comes later.
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
                model_bottom = max(py for _px, py in placed)
                bottom = model_bottom if bottom is None else max(bottom, model_bottom)
                break
    return count, bottom


def _discover_next(context: dict, column: int, row_index: int, search_y: int, models) -> CachedRowBoundary:
    left, column_top, right, column_bottom = _column_bounds(context, column)
    start_y = max(column_top, search_y)
    raw = _raw_ink(context, left=left, right=right, top=start_y, bottom=column_bottom)
    page_candidates = cached._bound_page_candidates(models)

    # Scan downwards. At each y, only ink near the column's lexical left edge
    # may propose a row. A proposal may yield several baselines; following
    # glyph evidence chooses among them rather than a geometric heuristic.
    start_slack = 40
    for anchor_y in range(start_y, column_bottom):
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
                    if baseline < start_y:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if placed and placed.issubset(raw):
                        hypotheses.add(baseline)
            if not hypotheses:
                continue
            scored = []
            for baseline in sorted(hypotheses):
                score, bottom = _baseline_score(raw, baseline, models, left, right)
                scored.append((score, baseline, bottom))
            best_score = max(score for score, _baseline, _bottom in scored)
            best = [(baseline, bottom) for score, baseline, bottom in scored if score == best_score]
            if best_score > 0 and len(best) == 1:
                baseline, bottom = best[0]
                next_search_y = max(baseline + 1, (bottom + 1) if bottom is not None else 0)
                return CachedRowBoundary(row_index, baseline, bottom, next_search_y)
    raise RuntimeError(
        f"sequential raw-page discovery stopped at column={column} row={row_index}: "
        f"no unique baseline from y={start_y}"
    )


def ensure_row_cached(context: dict, column: int, target_row: int, models) -> list[CachedRowBoundary]:
    if target_row < 0:
        raise ValueError("target_row must be >= 0")
    cache = _cache(context).setdefault(column, [])
    _left, column_top, _right, _bottom = _column_bounds(context, column)
    while len(cache) <= target_row:
        row_index = len(cache)
        search_y = column_top if not cache else cache[-1].next_search_y
        cache.append(_discover_next(context, column, row_index, search_y, models))
    return cache


def cached_row(context: dict, column: int, row: int, models) -> CachedRowBoundary:
    return ensure_row_cached(context, column, row, models)[row]
