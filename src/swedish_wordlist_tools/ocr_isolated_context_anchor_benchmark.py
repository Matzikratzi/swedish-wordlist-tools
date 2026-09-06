from __future__ import annotations

"""Benchmark a strictly isolated in-row context anchor.

This wraps :mod:`ocr_context_anchor_benchmark` but tightens anchor detection:
a candidate ``¤`` must match its facit raster exactly as a subset of the row and
must have a two-pixel white moat around its complete bounding box.  The anchor
still only proposes a baseline; the whole row must subsequently be solved by
exact cover.  If no isolated anchor baseline succeeds, the ordinary fast path
is used unchanged.
"""

from collections import Counter
from typing import Iterable

from . import ocr_context_anchor_benchmark as context_anchor
from .ocr_glyph_matcher import GlyphModel


WHITE_MOAT = 2
_ISOLATION_STATS: Counter[str] = Counter()


def _white_moat(
    ink: frozenset[tuple[int, int]],
    placed: frozenset[tuple[int, int]],
) -> bool:
    """Require a WHITE_MOAT-pixel white rectangular ring around ``placed``."""
    if not placed:
        return False
    xs = [x for x, _y in placed]
    ys = [y for _x, y in placed]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    outer_min_x = min_x - WHITE_MOAT
    outer_max_x = max_x + WHITE_MOAT
    outer_min_y = min_y - WHITE_MOAT
    outer_max_y = max_y + WHITE_MOAT

    for x, y in ink:
        if not (outer_min_x <= x <= outer_max_x and outer_min_y <= y <= outer_max_y):
            continue
        inside_box = min_x <= x <= max_x and min_y <= y <= max_y
        if inside_box:
            continue
        return False
    return True


def _isolated_anchor_baseline_hypotheses(
    ink: frozenset[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
) -> list[tuple[int, int, str]]:
    """Return baseline hypotheses only from exactly placed, isolated ``¤`` glyphs."""
    hypotheses: list[tuple[int, int, str]] = []
    raw_subset_hits = 0
    isolated_hits = 0

    for model in models:
        if model.label != context_anchor.ANCHOR_LABEL or not model.pixels:
            continue
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple((x, y) for x, y in model.pixels if x == min_x)
        for anchor_x, anchor_y in sorted(ink):
            for _mx, my in left_pixels:
                x0 = anchor_x - min_x
                baseline = anchor_y - my
                if x0 < 0 or x0 + model.width > width:
                    continue
                if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                    continue
                placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
                if not placed.issubset(ink):
                    continue
                raw_subset_hits += 1
                if not _white_moat(ink, placed):
                    continue
                isolated_hits += 1
                hypotheses.append((baseline, x0, str(model.style)))

    _ISOLATION_STATS["calls"] += 1
    _ISOLATION_STATS["raw_subset_hits"] += raw_subset_hits
    _ISOLATION_STATS["isolated_hits"] += isolated_hits
    if raw_subset_hits:
        _ISOLATION_STATS["calls_with_raw_hit"] += 1
    if isolated_hits:
        _ISOLATION_STATS["calls_with_isolated_hit"] += 1

    # Same policy as the original context-anchor benchmark: leftmost placement
    # first, and at most one full-row attempt per distinct baseline.
    hypotheses.sort(key=lambda item: (item[1], item[0], item[2]))
    seen: set[int] = set()
    unique: list[tuple[int, int, str]] = []
    for baseline, x0, style in hypotheses:
        if baseline in seen:
            continue
        seen.add(baseline)
        unique.append((baseline, x0, style))
    _ISOLATION_STATS["unique_baselines"] += len(unique)
    return unique


def _print_isolation_stats() -> None:
    raw = _ISOLATION_STATS["raw_subset_hits"]
    isolated = _ISOLATION_STATS["isolated_hits"]
    rejected = raw - isolated
    reject_pct = (100.0 * rejected / raw) if raw else 0.0
    print(
        "isolated-context-anchor-summary: "
        f"moat={WHITE_MOAT} calls={_ISOLATION_STATS['calls']} "
        f"calls_with_raw_hit={_ISOLATION_STATS['calls_with_raw_hit']} "
        f"calls_with_isolated_hit={_ISOLATION_STATS['calls_with_isolated_hit']} "
        f"raw_subset_hits={raw} isolated_hits={isolated} rejected={rejected} "
        f"reject_pct={reject_pct:.1f} unique_baselines={_ISOLATION_STATS['unique_baselines']}",
        flush=True,
    )


def main() -> int:
    original_hypotheses = context_anchor._anchor_baseline_hypotheses
    context_anchor._anchor_baseline_hypotheses = _isolated_anchor_baseline_hypotheses
    try:
        result = context_anchor.main()
    finally:
        context_anchor._anchor_baseline_hypotheses = original_hypotheses
    _print_isolation_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
