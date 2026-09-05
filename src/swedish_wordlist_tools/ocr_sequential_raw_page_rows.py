from __future__ import annotations

"""Sequential baseline discovery with a cache for random row access.

The new scanner is intentionally column-first: discover row 0, then row 1,
and so on.  A requested later row is reached by extending the cache only as
far as necessary.  Cached entries are discoveries, not legacy row crops.
"""

from dataclasses import dataclass

from .ocr_raw_page_baseline_row import match_row_from_raw_page


@dataclass(frozen=True)
class CachedRowBoundary:
    row: int
    baseline: int
    content_bottom: int | None
    next_search_y: int


def _cache(context: dict) -> dict[int, list[CachedRowBoundary]]:
    return context.setdefault("raw_page_row_boundary_cache", {})


def ensure_row_cached(context: dict, column: int, target_row: int, models) -> list[CachedRowBoundary]:
    """Discover rows from the top until target_row has a cached baseline.

    During this first transition we still call the raw-page matcher with the
    legacy row *index* to obtain row-start typography hints.  Crucially, the
    cached baseline/content bottom become the sequential state and callers no
    longer jump directly to a later row's geometry.  The next step can remove
    the remaining row-index hint once the three lexical start x positions are
    represented explicitly.
    """
    if target_row < 0:
        raise ValueError("target_row must be >= 0")
    cache = _cache(context).setdefault(column, [])
    while len(cache) <= target_row:
        row_index = len(cache)
        result = match_row_from_raw_page(context, (column, row_index), models)
        baseline = result.get("baseline")
        if baseline is None:
            raise RuntimeError(
                f"sequential raw-page discovery stopped at column={column} row={row_index}: "
                f"{result.get('reason')} candidates={result.get('candidate_baselines')}"
            )
        content_bottom = result.get("matched_bottom")
        # Search for the following row strictly below this established
        # baseline/content. This is cached now so random-access debug does not
        # need to rediscover earlier rows.
        next_search_y = max(int(baseline) + 1, int(content_bottom) + 1 if content_bottom is not None else 0)
        cache.append(CachedRowBoundary(row_index, int(baseline), content_bottom, next_search_y))
    return cache


def cached_row(context: dict, column: int, row: int, models) -> CachedRowBoundary:
    return ensure_row_cached(context, column, row, models)[row]
