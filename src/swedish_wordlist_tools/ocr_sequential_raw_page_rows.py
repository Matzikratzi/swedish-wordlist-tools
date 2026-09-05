from __future__ import annotations

"""Sequential baseline discovery directly from the page pixel array.

The first row may be seeded from raw-page layout geometry: absolute column
left/right plus the independently discovered row-0 top. Later rows are found
from the previous row's vertical start and horizontal start coordinate: the
probe first has to leave the previous row, cross a real white gap, and then
enter new ink near the left edge. Only then may a glyph establish a new
baseline.

A row still has a generous provisional bottom while it is solved. Its final
bottom is tightened only after the complete fixed-baseline row walk.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from .ocr_raw_page_baseline_row import _raw_ink


HOMONYM_PROBE_WIDTH = 12


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    row_top: int
    start_x: int
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
    """Return absolute raw-page bounds (left, top, right, bottom).

    A caller may provide ``raw_page_column_layout`` discovered directly from the
    source pixels. That is authoritative and avoids all legacy row geometry.
    The old row-map fallback remains temporarily for pages whose raw layout has
    not yet been wired in.
    """
    owners = context["pixel_owners"]
    raw_layout = context.get("raw_page_column_layout") or {}
    raw_column = raw_layout.get(column)
    if raw_column is not None:
        left = max(0, int(raw_column["left"]))
        right = min(owners.width, int(raw_column["right"]))
        top = max(0, int(raw_column["row0_top"]))
        bottom = min(owners.height, int(raw_column.get("bottom", owners.height)))
        return left, top, right, bottom

    entry = context["row_map"]["columns"][column]
    left = int(entry.get("crop_left", entry.get("left", 0)))
    right = int(entry.get("crop_right", entry.get("right", owners.width)))
    rows = entry.get("rows") or []
    # Transitional fallback only: old row geometry supplies the outer column
    # extent, never an individual row boundary or jump target.
    top = max(0, min((int(r["page_top"]) for r in rows), default=0) - 12)
    bottom = min(owners.height, max((int(r["page_bottom"]) for r in rows), default=owners.height) + 12)
    return left, top, right, bottom


def _provisional_height(models) -> int:
    """Generous local work height derived from glyph models, not row geometry."""
    heights = [int(getattr(model, "height", 0) or 0) for model in models]
    tallest = max(heights, default=16)
    return max(24, tallest + 12)


def _start_band(left: int, previous_start_x: int | None) -> tuple[int, int]:
    """Return the narrow lexical-start band used only for row discovery."""
    return left, left + 40


def _row_has_start_ink(context: dict, y: int, x0: int, x1: int) -> bool:
    owners = context["pixel_owners"]
    if y < 0 or y >= owners.height:
        return False
    x0 = max(0, x0)
    x1 = min(owners.width, x1)
    base = y * owners.width
    data = owners.data
    return any(data[base + x] != 0 for x in range(x0, x1))


def _find_next_row_top(
    context: dict,
    *,
    column_top: int,
    column_bottom: int,
    left: int,
    previous: CachedRowBoundary | None,
) -> int:
    """Lower the left-edge probe until it enters a new printed row.

    If raw page layout supplied row zero, ``column_top`` is already the proven
    first ink row and is returned unchanged. For later rows we begin at the
    previous row top, require a small completely white vertical gap in the
    lexical-start band, and only then accept the next ink row.
    """
    band_left, band_right = _start_band(left, None if previous is None else previous.start_x)
    if previous is None:
        if context.get("raw_page_column_layout"):
            return column_top
        for y in range(column_top, column_bottom):
            if _row_has_start_ink(context, y, band_left, band_right):
                return y
        raise RuntimeError("no start ink found in column")

    blank_run = 0
    saw_previous_ink = False
    for y in range(previous.row_top, column_bottom):
        has_ink = _row_has_start_ink(context, y, band_left, band_right)
        if has_ink:
            if saw_previous_ink and blank_run >= 2:
                return y
            saw_previous_ink = True
            blank_run = 0
        elif saw_previous_ink:
            blank_run += 1
    raise RuntimeError(
        f"no next left-edge ink after row={previous.row} top={previous.row_top}"
    )


def _walk_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
) -> tuple[int, set[tuple[int, int]], int]:
    """Consume one printed row left-to-right on one fixed baseline."""
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

        later_x = [x for x, _y in remaining if x > cursor]
        if not later_x:
            break
        cursor = min(later_x)

    return matched_glyphs, owned, matched_right


def _homonym_seed_walks(
    raw: set[tuple[int, int]],
    row_top: int,
    provisional_bottom: int,
    models,
    left: int,
    right: int,
) -> dict[tuple[int, int], tuple[tuple[int, int, int], int, int, set[tuple[int, int]], int, int]]:
    """Try the homonym coordinate first and use a matched digit as baseline seed.

    We only inspect a narrow absolute x strip at the column's left edge and only
    test models from the prepared homonym bucket. A complete homonym glyph match
    gives one or more baseline candidates; those candidates are then verified by
    walking the whole row on the same baseline.
    """
    page_candidates = cached._bound_page_candidates(models)
    if not page_candidates.homonym:
        return {}

    probe_right = min(right, left + HOMONYM_PROBE_WIDTH)
    candidate_rows = range(row_top, min(provisional_bottom, row_top + 12))
    seeds: set[tuple[int, int]] = set()

    for anchor_y in candidate_rows:
        xs = sorted(x for x, y in raw if y == anchor_y and left <= x < probe_right)
        for anchor_x in xs:
            for model, min_x, left_pixels in page_candidates.homonym:
                x0 = anchor_x - min_x
                if x0 < left or x0 + model.width > probe_right:
                    continue
                for _mx, my in left_pixels:
                    baseline = anchor_y - my
                    if baseline < row_top or baseline >= provisional_bottom:
                        continue
                    placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                    if placed and placed.issubset(raw):
                        seeds.add((anchor_x, baseline))

    walks = {}
    for anchor_x, baseline in sorted(seeds):
        glyphs, owned, matched_right = _walk_baseline(
            raw, baseline, models, left, right, anchor_x
        )
        if glyphs <= 0 or not owned:
            continue
        score = (matched_right - anchor_x, glyphs, len(owned))
        walks[(anchor_x, baseline)] = (
            score,
            anchor_x,
            baseline,
            owned,
            glyphs,
            matched_right,
        )
    return walks


def _discover_at_top(
    context: dict,
    column: int,
    row_index: int,
    row_top: int,
    previous: CachedRowBoundary | None,
    models,
) -> CachedRowBoundary:
    left, _column_top, right, column_bottom = _column_bounds(context, column)
    provisional_bottom = min(column_bottom, row_top + _provisional_height(models))
    raw = _raw_ink(context, left=left, right=right, top=row_top, bottom=provisional_bottom)
    page_candidates = cached._bound_page_candidates(models)
    band_left, band_right = _start_band(left, None if previous is None else previous.start_x)

    # If the row carries ink at the homonym coordinate, try only the known
    # homonym models there first. A successful digit acts as a cheap baseline
    # probe and lets us avoid the much larger generic first-glyph search.
    candidate_walks = _homonym_seed_walks(
        raw,
        row_top,
        provisional_bottom,
        models,
        left,
        right,
    )

    # Fall back to the global search only when no complete homonym seed could be
    # verified. Do not accept the first locally unique glyph fit: tiny models can
    # match accidental pixels near the roof.
    if not candidate_walks:
        candidate_walks = {}
        candidate_rows = range(row_top, min(provisional_bottom, row_top + 12))
        for anchor_y in candidate_rows:
            xs = [x for x, y in raw if y == anchor_y and band_left <= x < band_right]
            if previous is None:
                xs.sort()
            else:
                xs.sort(key=lambda x: (abs(x - previous.start_x), x))

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

                for baseline in hypotheses:
                    key = (anchor_x, baseline)
                    if key in candidate_walks:
                        continue
                    glyphs, owned, matched_right = _walk_baseline(
                        raw, baseline, models, left, right, anchor_x
                    )
                    if glyphs <= 0 or not owned:
                        continue
                    score = (matched_right - anchor_x, glyphs, len(owned))
                    candidate_walks[key] = (
                        score,
                        anchor_x,
                        baseline,
                        owned,
                        glyphs,
                        matched_right,
                    )

    if not candidate_walks:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"no starting glyph from left-edge top={row_top}"
        )

    best_score = max(item[0] for item in candidate_walks.values())
    best = [item for item in candidate_walks.values() if item[0] == best_score]
    if len(best) != 1:
        alternatives = sorted(
            (anchor_x, baseline, score)
            for score, anchor_x, baseline, _owned, _glyphs, _right in best
        )
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"ambiguous global baseline from top={row_top}: {alternatives}"
        )

    _score, anchor_x, baseline, owned, glyphs, matched_right = best[0]
    final_bottom = max(y for _x, y in owned) + 1
    return CachedRowBoundary(
        row=row_index,
        row_top=row_top,
        start_x=anchor_x,
        provisional_bottom=provisional_bottom,
        baseline=baseline,
        final_bottom=final_bottom,
        next_search_y=final_bottom,
        matched_glyphs=glyphs,
        matched_pixels=len(owned),
        matched_right=matched_right,
    )


def ensure_row_cached(context: dict, column: int, target_row: int, models) -> list[CachedRowBoundary]:
    if target_row < 0:
        raise ValueError("target_row must be >= 0")
    cache = _cache(context).setdefault(column, [])
    left, column_top, _right, column_bottom = _column_bounds(context, column)
    while len(cache) <= target_row:
        row_index = len(cache)
        previous = cache[-1] if cache else None
        row_top = _find_next_row_top(
            context,
            column_top=column_top,
            column_bottom=column_bottom,
            left=left,
            previous=previous,
        )
        cache.append(_discover_at_top(context, column, row_index, row_top, previous, models))
    return cache


def cached_row(context: dict, column: int, row: int, models) -> CachedRowBoundary:
    return ensure_row_cached(context, column, row, models)[row]
