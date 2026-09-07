from __future__ import annotations

"""Experimental context-anchor benchmark for exact-cover OCR.

A distinctive glyph inside the row (default: ``¤``) is used only to propose
baseline hypotheses. No source pixels are pre-owned by the anchor. For each
hypothesis the normal left-to-right exact-cover search is run with that baseline
fixed from the first non-homonym glyph. If all anchored hypotheses fail, the
ordinary page-cached fast path is used unchanged.

This is deliberately an ordering experiment, not a relaxation of OCR exactness.
"""

from collections import Counter
from dataclasses import dataclass
from time import perf_counter
from typing import Iterable

from . import ocr_fast_regression_scan as fast_regression
from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_split_facit_benchmark import main as split_benchmark_main


ANCHOR_LABEL = "¤"
_STATS: Counter[str] = Counter()
_BASELINES: Counter[int] = Counter()


@dataclass
class _Attempt:
    baseline: int
    anchor_x: int
    anchor_style: str
    states: int
    placements: int
    elapsed: float
    success: bool


_ATTEMPTS: list[_Attempt] = []


def _anchor_baseline_hypotheses(
    ink: frozenset[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
) -> list[tuple[int, int, str]]:
    hypotheses: list[tuple[int, int, str]] = []
    for model in models:
        if model.label != ANCHOR_LABEL or not model.pixels:
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
                if placed.issubset(ink):
                    hypotheses.append((baseline, x0, str(model.style)))

    hypotheses.sort(key=lambda item: (item[1], item[0], item[2]))
    seen: set[int] = set()
    unique: list[tuple[int, int, str]] = []
    for baseline, x0, style in hypotheses:
        if baseline in seen:
            continue
        seen.add(baseline)
        unique.append((baseline, x0, style))
    return unique


def _fixed_baseline_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    fixed_baseline: int,
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int, int] | None:
    """Normal anchored exact cover, but with baseline known from the outset."""
    if not ink:
        return None

    page_candidates = cached._bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], bool, int | None]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        previous_style: str | None,
        leading_homonym_seen: bool,
        previous_right: int | None,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, leading_homonym_seen, previous_right)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)

        for model, min_x, left_pixels in cached._iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=True,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                is_leading_homonym = (
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
                )
                if not is_leading_homonym and candidate_baseline != fixed_baseline:
                    continue
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue

                placements_tested += 1
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
                if not placed.issubset(remaining):
                    continue
                if not cached.placement_advances_right(placed, previous_right):
                    continue

                match = Match(
                    label=model.label,
                    style=model.style,
                    x=x0,
                    baseline=candidate_baseline,
                    pixels=placed,
                    model_pixels=len(model.pixels),
                    sources=model.sources,
                )
                tail = search(
                    frozenset(remaining.difference(placed)),
                    priority._typographic_style(model.style),
                    leading_homonym_seen or is_leading_homonym,
                    cached._placed_right(placed),
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, False, None)
    if chosen is None:
        return None
    selected = sorted(
        chosen,
        key=lambda match: (match.x, match.baseline, match.label, str(match.style)),
    )
    return fixed_baseline, selected, placements_tested, states


def _context_anchor_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
):
    frozen_ink = frozenset(ink)
    hypotheses = _anchor_baseline_hypotheses(frozen_ink, width, height, models)
    _STATS["calls"] += 1
    _STATS["hypotheses"] += len(hypotheses)
    if hypotheses:
        _STATS["calls_with_anchor"] += 1

    for baseline, anchor_x, anchor_style in hypotheses:
        started = perf_counter()
        result = _fixed_baseline_exact_cover(
            ink,
            width,
            height,
            models,
            baseline,
            max_states=max_states,
        )
        elapsed = perf_counter() - started
        _BASELINES[baseline] += 1
        if result is None:
            _STATS["anchor_misses"] += 1
            _ATTEMPTS.append(
                _Attempt(baseline, anchor_x, anchor_style, 0, 0, elapsed, False)
            )
            continue

        baseline_out, selected, placements, states = result
        _STATS["anchor_successes"] += 1
        _STATS["anchor_placements"] += placements
        _STATS["anchor_states"] += states
        _ATTEMPTS.append(
            _Attempt(baseline, anchor_x, anchor_style, states, placements, elapsed, True)
        )
        return baseline_out, selected, placements

    _STATS["ordinary_fallbacks"] += 1
    return _ORIGINAL(ink, width, height, models, max_states=max_states)


def _print_stats() -> None:
    print(
        "context-anchor-summary: "
        f"calls={_STATS['calls']} calls_with_anchor={_STATS['calls_with_anchor']} "
        f"hypotheses={_STATS['hypotheses']} anchor_successes={_STATS['anchor_successes']} "
        f"anchor_misses={_STATS['anchor_misses']} ordinary_fallbacks={_STATS['ordinary_fallbacks']} "
        f"anchor_states={_STATS['anchor_states']} anchor_placements={_STATS['anchor_placements']}",
        flush=True,
    )
    for rank, (baseline, count) in enumerate(_BASELINES.most_common(10), start=1):
        print(
            f"context-anchor-baseline: rank={rank} baseline={baseline} attempts={count}",
            flush=True,
        )
    if _ATTEMPTS:
        print("context-anchor-attempts: top=20 slowest", flush=True)
        for rank, attempt in enumerate(
            sorted(_ATTEMPTS, key=lambda row: row.elapsed, reverse=True)[:20], start=1
        ):
            print(
                f"context-anchor-attempt: rank={rank} baseline={attempt.baseline} "
                f"anchor_x={attempt.anchor_x} anchor_style={attempt.anchor_style!r} "
                f"states={attempt.states} placements={attempt.placements} "
                f"time={attempt.elapsed:.6f}s result={'success' if attempt.success else 'miss'}",
                flush=True,
            )


_ORIGINAL = fast_regression.page_cached_prioritized_fast_exact_cover


def main() -> int:
    fast_regression.page_cached_prioritized_fast_exact_cover = _context_anchor_exact_cover
    try:
        result = split_benchmark_main()
    finally:
        fast_regression.page_cached_prioritized_fast_exact_cover = _ORIGINAL
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
