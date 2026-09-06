from __future__ import annotations

"""Experimental result-neutral exact-cover ordering for diacritic supersets.

If an exact candidate raster is a strict subset of another facit raster in the
same typographic style, try the larger raster immediately at the same x/baseline
before recursing on the smaller one.  This is intended to catch families such as
o -> ö and a -> å/ä/á/à directly from raster geometry, without hard-coded
Unicode knowledge.  The normal OCR implementation is not modified; this module
monkey-patches the page-cached fast path only for this benchmark process.
"""

from collections import Counter
from typing import Iterable

from . import ocr_fast_regression_scan as fast_regression
from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_split_facit_benchmark import main as split_benchmark_main


_STATS: Counter[str] = Counter()
_LABEL_PAIRS: Counter[tuple[str, str]] = Counter()
_SUPERSET_CACHE_KEY: tuple[int, ...] | None = None
_SUPERSET_CACHE: dict[int, tuple[GlyphModel, ...]] = {}
_MAP_REPORTED = False


def _model_key(model: GlyphModel) -> tuple[int, int, str, str]:
    return (-len(model.pixels), -int(model.sources), model.label, str(model.style))


def _build_superset_map(models: Iterable[GlyphModel]) -> dict[int, tuple[GlyphModel, ...]]:
    global _SUPERSET_CACHE_KEY, _SUPERSET_CACHE, _MAP_REPORTED

    rows = tuple(model for model in models if model.pixels)
    key = tuple(id(model) for model in rows)
    if key == _SUPERSET_CACHE_KEY:
        return _SUPERSET_CACHE

    out: dict[int, tuple[GlyphModel, ...]] = {}
    pair_counts: Counter[tuple[str, str]] = Counter()
    strict_pairs = 0
    bases = 0

    for base in rows:
        base_pixels = frozenset(base.pixels)
        base_style = priority._typographic_style(base.style)
        supersets = []
        for larger in rows:
            if larger is base:
                continue
            if priority._typographic_style(larger.style) != base_style:
                continue
            larger_pixels = frozenset(larger.pixels)
            if base_pixels < larger_pixels:
                supersets.append(larger)
                strict_pairs += 1
                pair_counts[(base.label, larger.label)] += 1
        if supersets:
            bases += 1
            supersets.sort(key=_model_key)
            out[id(base)] = tuple(supersets)

    _SUPERSET_CACHE_KEY = key
    _SUPERSET_CACHE = out
    if not _MAP_REPORTED:
        _MAP_REPORTED = True
        print(
            f"superset-map: models={len(rows)} base_models={bases} strict_pairs={strict_pairs} "
            f"label_pairs={len(pair_counts)}",
            flush=True,
        )
        for rank, ((small, large), count) in enumerate(pair_counts.most_common(20), start=1):
            print(
                f"superset-map-pair: rank={rank} small={small!r} large={large!r} models={count}",
                flush=True,
            )
    return out


def _experimental_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    if not ink:
        return None

    page_candidates = cached._bound_page_candidates(models)
    supersets_by_id = _build_superset_map(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    priority_stats = priority._stats()
    priority_stats["calls"] += 1
    priority_stats[f"{row_kind}_hints"] += 1

    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
    states = 0
    placements_tested = 0

    def descend(
        model: GlyphModel,
        placed: frozenset[tuple[int, int]],
        remaining: frozenset[tuple[int, int]],
        x0: int,
        candidate_baseline: int,
        baseline: int | None,
        first_glyph: bool,
        leading_homonym_seen: bool,
    ) -> tuple[Match, ...] | None:
        is_leading_homonym = (
            first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
        )
        match = Match(
            label=model.label,
            style=model.style,
            x=x0,
            baseline=candidate_baseline,
            pixels=placed,
            model_pixels=len(model.pixels),
            sources=model.sources,
        )
        if is_leading_homonym:
            next_baseline = None
            saw_homonym = True
        else:
            next_baseline = candidate_baseline if baseline is None else baseline
            saw_homonym = leading_homonym_seen
        tail = search(
            frozenset(remaining.difference(placed)),
            next_baseline,
            priority._typographic_style(model.style),
            saw_homonym,
        )
        if tail is None:
            return None
        record_model_hit(model)
        return (match,) + tail

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, baseline, leading_homonym_seen)
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
            baseline_established=baseline is not None,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                if baseline is not None and candidate_baseline != baseline:
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

                larger_models = supersets_by_id.get(id(model), ())
                if larger_models:
                    _STATS["subset_hits"] += 1
                    for larger in larger_models:
                        placements_tested += 1
                        _STATS["superset_tests"] += 1
                        if x0 < 0 or x0 + larger.width > width:
                            continue
                        if candidate_baseline < -larger.min_y:
                            continue
                        if candidate_baseline > height - 1 - larger.max_y:
                            continue
                        larger_placed = frozenset(
                            (x0 + x, candidate_baseline + y) for x, y in larger.pixels
                        )
                        if not larger_placed.issubset(remaining):
                            continue
                        _STATS["superset_fits"] += 1
                        _LABEL_PAIRS[(model.label, larger.label)] += 1
                        promoted = descend(
                            larger,
                            larger_placed,
                            remaining,
                            x0,
                            candidate_baseline,
                            baseline,
                            first_glyph,
                            leading_homonym_seen,
                        )
                        if promoted is not None:
                            _STATS["superset_wins"] += 1
                            return promoted

                ordinary = descend(
                    model,
                    placed,
                    remaining,
                    x0,
                    candidate_baseline,
                    baseline,
                    first_glyph,
                    leading_homonym_seen,
                )
                if ordinary is not None:
                    return ordinary

        failed.add(state)
        return None

    chosen = search(target, None, None, False)
    _STATS["calls"] += 1
    _STATS["states"] += states
    _STATS["placements_tested"] += placements_tested
    priority_stats["placements_tested"] += placements_tested
    if chosen is None:
        _STATS["misses"] += 1
        return None

    selected = sorted(
        chosen,
        key=lambda match: (match.x, match.baseline, match.label, str(match.style)),
    )
    if row_kind == "homonym" and selected and priority._is_homonym_match(selected[0]):
        normal = next(
            (match for match in selected[1:] if not priority._is_homonym_match(match)),
            None,
        )
        baseline_out = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline_out = selected[0].baseline

    _STATS["successes"] += 1
    priority_stats["successful_calls"] += 1
    return baseline_out, selected, placements_tested


def _print_stats() -> None:
    print(
        "superset-priority-summary: "
        f"calls={_STATS['calls']} successes={_STATS['successes']} misses={_STATS['misses']} "
        f"states={_STATS['states']} placements={_STATS['placements_tested']} "
        f"subset_hits={_STATS['subset_hits']} superset_tests={_STATS['superset_tests']} "
        f"superset_fits={_STATS['superset_fits']} superset_wins={_STATS['superset_wins']}",
        flush=True,
    )
    for rank, ((small, large), count) in enumerate(_LABEL_PAIRS.most_common(20), start=1):
        print(
            f"superset-fit-pair: rank={rank} small={small!r} large={large!r} fits={count}",
            flush=True,
        )


def main() -> int:
    original = fast_regression.page_cached_prioritized_fast_exact_cover
    fast_regression.page_cached_prioritized_fast_exact_cover = _experimental_exact_cover
    try:
        result = split_benchmark_main()
    finally:
        fast_regression.page_cached_prioritized_fast_exact_cover = original
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
