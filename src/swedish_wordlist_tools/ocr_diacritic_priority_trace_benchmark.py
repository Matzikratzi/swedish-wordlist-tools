from __future__ import annotations

"""Benchmark a narrow diacritic-superset priority and trace expensive rows.

This is deliberately experimental and result-neutral. A larger glyph is promoted
only when it is a strict raster superset of a smaller glyph, has the same
horizontal extent, the same typography, and every extra pixel is above the
smaller glyph's top raster row. This captures facit-derived families such as
``o -> ö`` and ``a -> ä/å`` without treating generic shape inclusions such as
``i -> k`` or ``n -> m`` as diacritics.

The module monkey-patches only the fast exact-cover function for the benchmark
process. It also records per-row search states, placements, anchor positions and
most-tested candidate labels so the expensive row can be localized.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from . import ocr_fast_regression_scan as fast_regression
from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_split_facit_benchmark import main as split_benchmark_main


@dataclass
class RowTrace:
    calls: int = 0
    successes: int = 0
    misses: int = 0
    states: int = 0
    placements: int = 0
    subset_hits: int = 0
    superset_tests: int = 0
    superset_fits: int = 0
    superset_wins: int = 0
    anchors: Counter[tuple[int, int]] = field(default_factory=Counter)
    anchor_x: Counter[int] = field(default_factory=Counter)
    model_tests: Counter[str] = field(default_factory=Counter)
    subset_pairs: Counter[tuple[str, str]] = field(default_factory=Counter)


_CURRENT_POSITION: tuple[int, int] | None = None
_ROW_TRACES: dict[tuple[int, int, int], RowTrace] = defaultdict(RowTrace)
_GLOBAL = RowTrace()
_SUPERSET_CACHE_KEY: tuple[int, ...] | None = None
_SUPERSET_CACHE: dict[int, tuple[GlyphModel, ...]] = {}
_MAP_REPORTED = False


def _model_key(model: GlyphModel) -> tuple[int, int, str, str]:
    return (-len(model.pixels), -int(model.sources), model.label, str(model.style))


def _extent(model: GlyphModel) -> tuple[int, int, int]:
    xs = [int(x) for x, _y in model.pixels]
    ys = [int(y) for _x, y in model.pixels]
    return min(xs), max(xs), min(ys)


def _is_diacritic_superset(base: GlyphModel, larger: GlyphModel) -> bool:
    if larger is base:
        return False
    if priority._typographic_style(larger.style) != priority._typographic_style(base.style):
        return False
    base_pixels = frozenset((int(x), int(y)) for x, y in base.pixels)
    larger_pixels = frozenset((int(x), int(y)) for x, y in larger.pixels)
    if not base_pixels < larger_pixels:
        return False
    base_min_x, base_max_x, base_min_y = _extent(base)
    larger_min_x, larger_max_x, _larger_min_y = _extent(larger)
    if (larger_min_x, larger_max_x) != (base_min_x, base_max_x):
        return False
    extra = larger_pixels - base_pixels
    return bool(extra) and all(y < base_min_y for _x, y in extra)


def _build_superset_map(models: Iterable[GlyphModel]) -> dict[int, tuple[GlyphModel, ...]]:
    global _SUPERSET_CACHE_KEY, _SUPERSET_CACHE, _MAP_REPORTED
    rows = tuple(model for model in models if model.pixels)
    key = tuple(id(model) for model in rows)
    if key == _SUPERSET_CACHE_KEY:
        return _SUPERSET_CACHE

    out: dict[int, tuple[GlyphModel, ...]] = {}
    pairs: Counter[tuple[str, str]] = Counter()
    for base in rows:
        larger = [candidate for candidate in rows if _is_diacritic_superset(base, candidate)]
        if larger:
            larger.sort(key=_model_key)
            out[id(base)] = tuple(larger)
            for candidate in larger:
                pairs[(base.label, candidate.label)] += 1

    _SUPERSET_CACHE_KEY = key
    _SUPERSET_CACHE = out
    if not _MAP_REPORTED:
        _MAP_REPORTED = True
        print(
            f"diacritic-map: models={len(rows)} base_models={len(out)} "
            f"strict_pairs={sum(len(v) for v in out.values())} label_pairs={len(pairs)}",
            flush=True,
        )
        for rank, ((small, large), count) in enumerate(pairs.most_common(20), start=1):
            print(
                f"diacritic-map-pair: rank={rank} small={small!r} large={large!r} models={count}",
                flush=True,
            )
    return out


def _trace_for_current() -> RowTrace:
    if _CURRENT_POSITION is None:
        return _GLOBAL
    page = int(getattr(priority._tls, "trace_page", -1))
    return _ROW_TRACES[(page, int(_CURRENT_POSITION[0]), int(_CURRENT_POSITION[1]))]


def _bump(name: str, amount: int = 1) -> None:
    setattr(_GLOBAL, name, getattr(_GLOBAL, name) + amount)
    trace = _trace_for_current()
    if trace is not _GLOBAL:
        setattr(trace, name, getattr(trace, name) + amount)


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
    trace = _trace_for_current()
    _bump("calls")

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
        _bump("states")
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        trace.anchors[(anchor_x, anchor_y)] += 1
        trace.anchor_x[anchor_x] += 1
        if trace is not _GLOBAL:
            _GLOBAL.anchors[(anchor_x, anchor_y)] += 1
            _GLOBAL.anchor_x[anchor_x] += 1
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
                _bump("placements")
                trace.model_tests[model.label] += 1
                if trace is not _GLOBAL:
                    _GLOBAL.model_tests[model.label] += 1
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
                if not placed.issubset(remaining):
                    continue

                larger_models = supersets_by_id.get(id(model), ())
                if larger_models:
                    _bump("subset_hits")
                    for larger in larger_models:
                        placements_tested += 1
                        _bump("placements")
                        _bump("superset_tests")
                        if x0 + larger.width > width:
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
                        _bump("superset_fits")
                        trace.subset_pairs[(model.label, larger.label)] += 1
                        if trace is not _GLOBAL:
                            _GLOBAL.subset_pairs[(model.label, larger.label)] += 1
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
                            _bump("superset_wins")
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
    priority_stats["placements_tested"] += placements_tested
    if chosen is None:
        _bump("misses")
        return None

    _bump("successes")
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
    priority_stats["successful_calls"] += 1
    return baseline_out, selected, placements_tested


def _print_trace(label: str, trace: RowTrace) -> None:
    print(
        f"diacritic-trace: {label} calls={trace.calls} success={trace.successes} misses={trace.misses} "
        f"states={trace.states} placements={trace.placements} subset_hits={trace.subset_hits} "
        f"superset_tests={trace.superset_tests} superset_fits={trace.superset_fits} "
        f"superset_wins={trace.superset_wins}",
        flush=True,
    )
    for rank, (x, count) in enumerate(trace.anchor_x.most_common(10), start=1):
        print(f"diacritic-anchor-x: {label} rank={rank} x={x} states={count}", flush=True)
    for rank, (model, count) in enumerate(trace.model_tests.most_common(10), start=1):
        print(f"diacritic-model-test: {label} rank={rank} label={model!r} tests={count}", flush=True)
    for rank, ((small, large), count) in enumerate(trace.subset_pairs.most_common(10), start=1):
        print(
            f"diacritic-fit-pair: {label} rank={rank} small={small!r} large={large!r} fits={count}",
            flush=True,
        )


def _print_stats() -> None:
    _print_trace("all", _GLOBAL)
    print("diacritic-row-trace: top=10 by placements", flush=True)
    ordered = sorted(_ROW_TRACES.items(), key=lambda item: item[1].placements, reverse=True)
    for rank, ((page, column, row), trace) in enumerate(ordered[:10], start=1):
        print(
            f"diacritic-row: rank={rank} page={page} column={column} row={row} "
            f"calls={trace.calls} states={trace.states} placements={trace.placements} "
            f"subset_hits={trace.subset_hits} superset_fits={trace.superset_fits}",
            flush=True,
        )
    target = _ROW_TRACES.get((4, 1, 23))
    if target is not None:
        _print_trace("page=4 column=1 row=23", target)


def main() -> int:
    global _CURRENT_POSITION
    original_exact = fast_regression.page_cached_prioritized_fast_exact_cover
    original_load = page_editor._load_owned_row_state

    def traced_load(context, position, models, *args, **kwargs):
        global _CURRENT_POSITION
        previous = _CURRENT_POSITION
        _CURRENT_POSITION = (int(position[0]), int(position[1]))
        priority._tls.trace_page = int(context.get("page_number", -1))
        try:
            return original_load(context, position, models, *args, **kwargs)
        finally:
            _CURRENT_POSITION = previous

    fast_regression.page_cached_prioritized_fast_exact_cover = _experimental_exact_cover
    page_editor._load_owned_row_state = traced_load
    try:
        result = split_benchmark_main()
    finally:
        page_editor._load_owned_row_state = original_load
        fast_regression.page_cached_prioritized_fast_exact_cover = original_exact
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
