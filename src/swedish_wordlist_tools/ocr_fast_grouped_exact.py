from __future__ import annotations

"""Bounded exact matching for regression scans after whole-row fast-cover misses.

The row is split only at horizontal blank runs wider than any learned glyph can
cross.  Each independent group is then solved by the same page-cached fast
exact-cover matcher.  Results are accepted only when every source pixel is
covered and the normal-text baselines stay within one raster line.  There is no
exhaustive candidate generation here.
"""

from dataclasses import replace

from .ocr_glyph_gap_matcher import max_internal_blank_run, safe_ink_groups
from .ocr_page_cached_fast_path import page_cached_prioritized_fast_exact_cover


def fast_grouped_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models,
    *,
    baseline_slop: int = 1,
):
    """Return ``(baseline, matches, placements, groups)`` or ``None``.

    This is a success-only bounded path.  It never slides models exhaustively.
    A single group is deliberately not retried because the caller has already
    tried whole-row fast exact-cover.
    """
    if not ink:
        return None
    max_gap = max_internal_blank_run(models)
    groups = safe_ink_groups(ink, max_internal_gap=max_gap)
    if len(groups) <= 1:
        return None

    selected = []
    baselines: list[int] = []
    placements = 0
    for left, right, local_ink in groups:
        result = page_cached_prioritized_fast_exact_cover(
            local_ink,
            right - left,
            height,
            models,
        )
        if result is None:
            return None
        baseline, matches, tested = result
        baselines.append(int(baseline))
        placements += int(tested)
        for match in matches:
            selected.append(
                replace(
                    match,
                    x=int(match.x) + int(left),
                    pixels=frozenset((int(x) + int(left), int(y)) for x, y in match.pixels),
                )
            )

    if max(baselines) - min(baselines) > int(baseline_slop):
        return None

    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    if covered != ink:
        return None

    selected.sort(key=lambda match: (match.x, match.baseline, match.label, str(match.style)))
    baseline = sorted(baselines)[len(baselines) // 2]
    return baseline, selected, placements, len(groups)
