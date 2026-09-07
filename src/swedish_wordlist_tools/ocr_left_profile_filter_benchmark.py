from __future__ import annotations

"""Benchmark an exact left-profile rejection filter for the fast exact-cover path.

Once the shared row baseline is established, the leftmost remaining source pixel
(anchor_x, anchor_y) fixes the relative y coordinate that a candidate's leftmost
facit column must contain: rel_y = anchor_y - baseline.  Candidates whose
leftmost facit column lacks that rel_y cannot possibly cover the anchor and are
rejected before any placement is constructed.  Before baseline lock the search
is unchanged.

This module monkey-patches only for the benchmark process; normal OCR semantics
and files are untouched.
"""

from collections import Counter, defaultdict
from typing import Iterable

from . import ocr_fast_regression_scan as fast_regression
from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_split_facit_benchmark import main as split_benchmark_main


_CURRENT_POSITION: tuple[int, int] | None = None
_STATS: Counter[str] = Counter()
_ROW_STATS: dict[tuple[int, int, int], Counter[str]] = defaultdict(Counter)
_ROW_REL_Y: dict[tuple[int, int, int], Counter[int]] = defaultdict(Counter)
_ROW_LABEL_REJECT: dict[tuple[int, int, int], Counter[str]] = defaultdict(Counter)
_ROW_LABEL_KEEP: dict[tuple[int, int, int], Counter[str]] = defaultdict(Counter)


def _row_key() -> tuple[int, int, int] | None:
    if _CURRENT_POSITION is None:
        return None
    page = int(getattr(priority._tls, "trace_page", -1))
    return page, int(_CURRENT_POSITION[0]), int(_CURRENT_POSITION[1])


def _inc(name: str, amount: int = 1) -> None:
    _STATS[name] += amount
    key = _row_key()
    if key is not None:
        _ROW_STATS[key][name] += amount


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
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    stats = priority._stats()
    stats["calls"] += 1
    stats[f"{row_kind}_hints"] += 1

    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
    states = 0
    placements_tested = 0

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
        _inc("states")
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)
        rel_y = None if baseline is None else anchor_y - baseline
        key = _row_key()
        if rel_y is not None:
            _inc("baseline_locked_states")
            if key is not None:
                _ROW_REL_Y[key][int(rel_y)] += 1

        for model, min_x, left_pixels in cached._iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        ):
            _inc("candidate_models_seen")
            if rel_y is not None and not any(my == rel_y for _mx, my in left_pixels):
                _inc("left_profile_rejected")
                if key is not None:
                    _ROW_LABEL_REJECT[key][model.label] += 1
                continue
            if rel_y is not None:
                _inc("left_profile_kept")
                if key is not None:
                    _ROW_LABEL_KEEP[key][model.label] += 1

            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                is_leading_homonym = (
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
                )
                if baseline is not None and candidate_baseline != baseline:
                    continue
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue
                placements_tested += 1
                _inc("placements")
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
                if not placed.issubset(remaining):
                    continue
                _inc("placement_subset_fits")
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
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    _inc("calls")
    chosen = search(target, None, None, False)
    stats["placements_tested"] += placements_tested
    if chosen is None:
        _inc("misses")
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

    _inc("successes")
    stats["successful_calls"] += 1
    return baseline_out, selected, placements_tested


def _print_row(key: tuple[int, int, int], *, prefix: str) -> None:
    row = _ROW_STATS[key]
    seen = row["candidate_models_seen"]
    rejected = row["left_profile_rejected"]
    kept = row["left_profile_kept"]
    pct = 100.0 * rejected / seen if seen else 0.0
    print(
        f"left-profile-row: {prefix} page={key[0]} column={key[1]} row={key[2]} "
        f"calls={row['calls']} states={row['states']} locked_states={row['baseline_locked_states']} "
        f"models_seen={seen} rejected={rejected} kept={kept} reject_pct={pct:.1f} "
        f"placements={row['placements']} subset_fits={row['placement_subset_fits']} "
        f"success={row['successes']} misses={row['misses']}",
        flush=True,
    )
    for rank, (rel_y, count) in enumerate(_ROW_REL_Y[key].most_common(8), start=1):
        print(
            f"left-profile-rel-y: {prefix} page={key[0]} column={key[1]} row={key[2]} "
            f"rank={rank} rel_y={rel_y} states={count}",
            flush=True,
        )
    for rank, (label, count) in enumerate(_ROW_LABEL_REJECT[key].most_common(8), start=1):
        print(
            f"left-profile-reject-label: {prefix} page={key[0]} column={key[1]} row={key[2]} "
            f"rank={rank} label={label!r} rejected={count}",
            flush=True,
        )
    for rank, (label, count) in enumerate(_ROW_LABEL_KEEP[key].most_common(8), start=1):
        print(
            f"left-profile-keep-label: {prefix} page={key[0]} column={key[1]} row={key[2]} "
            f"rank={rank} label={label!r} kept={count}",
            flush=True,
        )


def _print_stats() -> None:
    seen = _STATS["candidate_models_seen"]
    rejected = _STATS["left_profile_rejected"]
    pct = 100.0 * rejected / seen if seen else 0.0
    print(
        "left-profile-summary: "
        f"calls={_STATS['calls']} successes={_STATS['successes']} misses={_STATS['misses']} "
        f"states={_STATS['states']} locked_states={_STATS['baseline_locked_states']} "
        f"models_seen={seen} rejected={rejected} kept={_STATS['left_profile_kept']} "
        f"reject_pct={pct:.1f} placements={_STATS['placements']} "
        f"subset_fits={_STATS['placement_subset_fits']}",
        flush=True,
    )
    ranked = sorted(
        _ROW_STATS,
        key=lambda key: _ROW_STATS[key]["placements"],
        reverse=True,
    )[:10]
    print("left-profile-row-trace: top=10 by placements", flush=True)
    for rank, key in enumerate(ranked, start=1):
        _print_row(key, prefix=f"rank={rank}")
    target = next((key for key in _ROW_STATS if key[1:] == (1, 23)), None)
    if target is not None:
        _print_row(target, prefix="target")


def main() -> int:
    global _CURRENT_POSITION

    original_cover = fast_regression.page_cached_prioritized_fast_exact_cover
    original_load = page_editor._load_owned_row_state
    original_build = page_editor.build_page_context_pixel_array

    def traced_build(*args, **kwargs):
        context = original_build(*args, **kwargs)
        priority._tls.trace_page = int(context.get("page_number", -1))
        return context

    def traced_load(context, position, models):
        global _CURRENT_POSITION
        previous = _CURRENT_POSITION
        _CURRENT_POSITION = (int(position[0]), int(position[1]))
        priority._tls.trace_page = int(context.get("page_number", -1))
        try:
            return original_load(context, position, models)
        finally:
            _CURRENT_POSITION = previous

    fast_regression.page_cached_prioritized_fast_exact_cover = _experimental_exact_cover
    page_editor._load_owned_row_state = traced_load
    page_editor.build_page_context_pixel_array = traced_build
    try:
        result = split_benchmark_main()
    finally:
        fast_regression.page_cached_prioritized_fast_exact_cover = original_cover
        page_editor._load_owned_row_state = original_load
        page_editor.build_page_context_pixel_array = original_build
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
