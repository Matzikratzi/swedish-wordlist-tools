from __future__ import annotations

"""Sequential baseline discovery directly from the page pixel array.

The stable vertical geometry is deliberately small:

* before row 0, derive one initial upper border from the first start-band ink;
* for row N > 0, the previous row's proven ``border`` is the upper boundary;
* search left-to-right through a short band below that boundary;
* solve the row on one baseline and derive the next ``border`` from proven ink.

There is no independently discovered row ``top`` or ``hint`` in this path.
``debug_top`` is retained only as a diagnostic description of solved glyph ink.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from .ocr_raw_page_baseline_row import _raw_ink


HOMONYM_PROBE_WIDTH = 12
FIRST_TEXT_SEARCH_WIDTH = 40
START_SEARCH_HEIGHT = 15
BASELINE_PROBE_GLYPHS = 3
PAGE1_EXACT_LABELS = frozenset({"a", "á", "à", "A", "Á", "À"})
PAGE1_X_LEFT_SLACK = 4
PAGE1_X_RIGHT_SLACK = 10


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    start_x: int
    baseline: int
    border: int
    debug_top: int
    matched_glyphs: int
    matched_pixels: int
    matched_right: int


def _cache(context: dict) -> dict[int, list[CachedRowBoundary]]:
    return context.setdefault("raw_page_row_boundary_cache", {})


def _column_bounds(context: dict, column: int) -> tuple[int, int, int, int]:
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
    top = max(0, min((int(r["page_top"]) for r in rows), default=0) - 12)
    bottom = min(
        owners.height,
        max((int(r["page_bottom"]) for r in rows), default=owners.height) + 12,
    )
    return left, top, right, bottom


def _provisional_height(models) -> int:
    heights = [int(getattr(model, "height", 0) or 0) for model in models]
    tallest = max(heights, default=16)
    return max(24, tallest + 12)


def _start_band(left: int, right: int) -> tuple[int, int]:
    return left, min(right, left + FIRST_TEXT_SEARCH_WIDTH)


def _first_ink_y(
    context: dict,
    *,
    search_from: int,
    search_to: int,
    left: int,
    right: int,
) -> int | None:
    """Find the first start-band ink row when entering a fresh column.

    Row 0 is the only row for which the upper boundary cannot come from a
    previous solved row.  On page 1 column 1 ``search_from`` is already below
    the black letter blotch, as supplied by the raw page-1 layout detector.
    """
    owners = context["pixel_owners"]
    x0, x1 = _start_band(left, right)
    for y in range(max(0, search_from), min(owners.height, search_to)):
        base = y * owners.width
        if any(owners.data[base + x] != 0 for x in range(x0, x1)):
            return y
    return None


def _initial_border(
    context: dict,
    *,
    column_top: int,
    column_bottom: int,
    left: int,
    right: int,
) -> int:
    first_y = _first_ink_y(
        context,
        search_from=column_top,
        search_to=column_bottom,
        left=left,
        right=right,
    )
    if first_y is None:
        raise RuntimeError("no start ink found in column")
    return first_y - 1


def _x_first_ink_x(
    raw: set[tuple[int, int]],
    *,
    search_from: int,
    search_limit: int,
    left: int,
    right: int,
    include_homonym: bool,
) -> int | None:
    """Return the leftmost ink x in the first 15 rows below the upper boundary.

    x is deliberately the outer loop and y the inner loop.  With
    ``include_homonym`` this is the true leftmost row-start ink.  The current
    glyph walker still needs an ordinary-text anchor as well, so callers may
    make a second pass excluding the homonym strip.
    """
    x0 = left if include_homonym else min(right, left + HOMONYM_PROBE_WIDTH)
    x1 = min(right, left + FIRST_TEXT_SEARCH_WIDTH)
    y1 = min(search_limit, search_from + START_SEARCH_HEIGHT)
    for x in range(x0, x1):
        for y in range(search_from, y1):
            if (x, y) in raw:
                return x
    return None


def _walk_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
    *,
    first_candidates=None,
    max_glyphs: int | None = None,
) -> tuple[int, set[tuple[int, int]], int]:
    """Consume printed glyphs left-to-right on one fixed baseline."""
    page_candidates = cached._bound_page_candidates(models)
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
            candidates = cached._iter_candidates(
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
            placed = {(x0 + mx, baseline + my) for mx, my in model.pixels}
            if placed and placed.issubset(remaining):
                chosen = (model, placed)
                break

        if chosen is not None:
            model, placed = chosen
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


def _bold_candidates(page_candidates, allowed_labels: frozenset[str] | None = None):
    return [
        candidate
        for candidate in page_candidates.bold
        if allowed_labels is None or candidate[0].label in allowed_labels
    ]


def _continuation_candidates(page_candidates):
    """Continuation rows usually start roman/italic; bold remains possible."""
    return (
        tuple(page_candidates.roman)
        + tuple(page_candidates.italic)
        + tuple(page_candidates.bold)
        + tuple(page_candidates.other)
    )


def _page1_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    first_ink_x: int,
):
    page_candidates = cached._bound_page_candidates(models)
    initial_candidates = _bold_candidates(page_candidates, PAGE1_EXACT_LABELS)
    walks = {}

    for model, min_x, _left_pixels in initial_candidates:
        x0_lo = max(left, first_ink_x - PAGE1_X_LEFT_SLACK)
        x0_hi = min(right - model.width, first_ink_x + PAGE1_X_RIGHT_SLACK)
        if x0_hi < x0_lo:
            continue
        for x0 in range(x0_lo, x0_hi + 1):
            for baseline in range(search_from, search_limit):
                placed = {(x0 + mx, baseline + my) for mx, my in model.pixels}
                if not placed or not placed.issubset(raw):
                    continue
                anchor_x = x0 + min_x
                follow_x = max(x for x, _y in placed) + 1
                glyphs, owned, matched_right = _walk_baseline(
                    raw,
                    baseline,
                    models,
                    left,
                    right,
                    follow_x,
                    max_glyphs=BASELINE_PROBE_GLYPHS,
                )
                if glyphs <= 0:
                    continue
                score = (
                    glyphs,
                    matched_right - anchor_x,
                    len(owned) + len(placed),
                )
                key = (anchor_x, baseline)
                value = (score, model, x0, placed, glyphs, matched_right)
                old = walks.get(key)
                if old is None or score > old[0]:
                    walks[key] = value
    return walks


def _ordinary_baseline_probe_walks(
    raw: set[tuple[int, int]],
    search_from: int,
    search_limit: int,
    models,
    left: int,
    right: int,
    anchor_x: int,
    first_candidates,
):
    """Build baseline hypotheses from the same 15-row band used for x-first.

    A baseline may lie below the band: only the anchor ink itself is restricted
    to the band.  This removes the old independent ``hint_y + 12`` gate.
    """
    hypotheses: set[int] = set()
    anchor_bottom = min(search_limit, search_from + START_SEARCH_HEIGHT)
    for anchor_y in range(search_from, anchor_bottom):
        if (anchor_x, anchor_y) not in raw:
            continue
        for model, min_x, left_pixels in first_candidates:
            x0 = anchor_x - min_x
            if x0 < left or x0 + model.width > right:
                continue
            for _mx, my in left_pixels:
                baseline = anchor_y - my
                if baseline < search_from or baseline >= search_limit:
                    continue
                placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
                if placed and placed.issubset(raw):
                    hypotheses.add(baseline)

    walks = {}
    for baseline in sorted(hypotheses):
        glyphs, owned, matched_right = _walk_baseline(
            raw,
            baseline,
            models,
            left,
            right,
            anchor_x,
            first_candidates=first_candidates,
            max_glyphs=BASELINE_PROBE_GLYPHS,
        )
        if glyphs <= 0 or not owned:
            continue
        score = (glyphs, matched_right - anchor_x, len(owned))
        walks[(anchor_x, baseline)] = (
            score,
            None,
            anchor_x,
            owned,
            glyphs,
            matched_right,
        )
    return walks


def _exact_first_candidates(raw, baseline, candidates, anchor_x, left, right):
    exact = []
    for candidate in candidates:
        model, min_x, _left_pixels = candidate
        x0 = anchor_x - min_x
        if x0 < left or x0 + model.width > right:
            continue
        placed = {(x0 + mx, baseline + my) for mx, my in model.pixels}
        if placed and placed.issubset(raw):
            exact.append((len(placed), candidate))
    exact.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _pixels, candidate in exact]


def _match_homonym_on_baseline(
    raw: set[tuple[int, int]],
    baseline: int,
    models,
    left: int,
    text_start_x: int,
) -> set[tuple[int, int]]:
    page_candidates = cached._bound_page_candidates(models)
    probe_right = min(text_start_x, left + HOMONYM_PROBE_WIDTH)
    if probe_right <= left:
        return set()
    best: set[tuple[int, int]] = set()
    for model, min_x, _left_pixels in page_candidates.homonym:
        for x0 in range(left - min_x, probe_right - min_x):
            placed = {(x0 + mx, baseline + py) for mx, py in model.pixels}
            if not placed:
                continue
            xs = [x for x, _y in placed]
            if min(xs) < left or max(xs) >= text_start_x:
                continue
            if placed.issubset(raw) and len(placed) > len(best):
                best = placed
    return best


def _discover_row(
    context: dict,
    column: int,
    row_index: int,
    upper_border: int,
    previous: CachedRowBoundary | None,
    models,
) -> CachedRowBoundary:
    left, _column_top, right, column_bottom = _column_bounds(context, column)
    search_from = upper_border + 1 if previous is None else upper_border
    search_limit = min(column_bottom, search_from + _provisional_height(models))
    raw = _raw_ink(
        context,
        left=left,
        right=right,
        top=search_from,
        bottom=search_limit,
    )

    # First preserve the true leftmost row-start evidence, including a homonym.
    row_start_x = _x_first_ink_x(
        raw,
        search_from=search_from,
        search_limit=search_limit,
        left=left,
        right=right,
        include_homonym=True,
    )
    if row_start_x is None:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"no start ink in y={search_from}..{search_from + START_SEARCH_HEIGHT - 1}"
        )

    # The existing baseline walker still starts on ordinary text.  This second
    # x-first pass is temporary until homonym/headword/continuation start classes
    # each have their own matcher strategy.
    first_ink_x = _x_first_ink_x(
        raw,
        search_from=search_from,
        search_limit=search_limit,
        left=left,
        right=right,
        include_homonym=False,
    )
    if first_ink_x is None:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"row_start_x={row_start_x} but no ordinary text anchor"
        )

    page1 = context.get("raw_page_layout_source") == "page1-raw-pixels"
    page_candidates = cached._bound_page_candidates(models)
    page1_headword_row0 = page1 and row_index == 0

    if page1_headword_row0:
        probe_first_candidates = tuple(
            _bold_candidates(page_candidates, PAGE1_EXACT_LABELS)
        )
        probe_walks = _page1_baseline_probe_walks(
            raw,
            search_from,
            search_limit,
            models,
            left,
            right,
            first_ink_x,
        )
    else:
        probe_first_candidates = _continuation_candidates(page_candidates)
        probe_walks = _ordinary_baseline_probe_walks(
            raw,
            search_from,
            search_limit,
            models,
            left,
            right,
            first_ink_x,
            probe_first_candidates,
        )

    if not probe_walks:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"no baseline probe near x={first_ink_x} upper_border={upper_border} "
            f"row_start_x={row_start_x}"
        )

    best_score = max(item[0] for item in probe_walks.values())
    best_keys = [key for key, item in probe_walks.items() if item[0] == best_score]
    if len(best_keys) != 1:
        alternatives = sorted((key, probe_walks[key][0]) for key in best_keys)
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"ambiguous baseline probe near x={first_ink_x}: {alternatives}"
        )

    text_start_x, baseline = best_keys[0]
    first_candidates = _exact_first_candidates(
        raw, baseline, probe_first_candidates, text_start_x, left, right
    )
    if not first_candidates:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"baseline={baseline} proved but no exact first glyph at x={text_start_x}"
        )

    glyphs, owned, matched_right = _walk_baseline(
        raw,
        baseline,
        models,
        left,
        right,
        text_start_x,
        first_candidates=first_candidates,
    )
    if glyphs <= 0 or not owned:
        raise RuntimeError(
            f"sequential raw-page discovery stopped at column={column} row={row_index}: "
            f"baseline={baseline} proved but full row walk failed"
        )

    homonym_owned = _match_homonym_on_baseline(
        raw, baseline, models, left, text_start_x
    )
    if homonym_owned:
        owned = set(owned)
        owned.update(homonym_owned)
        glyphs += 1

    debug_top = min(y for _x, y in owned)
    border = max(y for _x, y in owned) + 1
    return CachedRowBoundary(
        row=row_index,
        start_x=text_start_x,
        baseline=baseline,
        border=border,
        debug_top=debug_top,
        matched_glyphs=glyphs,
        matched_pixels=len(owned),
        matched_right=matched_right,
    )


def ensure_row_cached(
    context: dict, column: int, target_row: int, models
) -> list[CachedRowBoundary]:
    if target_row < 0:
        raise ValueError("target_row must be >= 0")
    cache = _cache(context).setdefault(column, [])
    left, column_top, right, column_bottom = _column_bounds(context, column)

    initial_border = context.setdefault("raw_page_initial_border_cache", {}).get(column)
    if initial_border is None:
        initial_border = _initial_border(
            context,
            column_top=column_top,
            column_bottom=column_bottom,
            left=left,
            right=right,
        )
        context["raw_page_initial_border_cache"][column] = initial_border

    while len(cache) <= target_row:
        row_index = len(cache)
        previous = cache[-1] if cache else None
        upper_border = initial_border if previous is None else previous.border
        cache.append(
            _discover_row(
                context,
                column,
                row_index,
                upper_border,
                previous,
                models,
            )
        )
    return cache


def cached_row(context: dict, column: int, row: int, models) -> CachedRowBoundary:
    return ensure_row_cached(context, column, row, models)[row]
