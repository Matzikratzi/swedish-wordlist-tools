from __future__ import annotations

"""Result-neutral tracing for the page-cached exact-cover fast path.

This is intentionally the same search as ``page_cached_prioritized_fast_exact_cover``
with counters around the recursive search.  Only calls slower than the configured
threshold are printed.  Search order, state budget and accepted result are unchanged.
"""

from time import perf_counter
from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_page_cached_fast_path import _bound_page_candidates, _iter_candidates


_TRACE_SECONDS = 0.2


def set_trace_row(page: int | None, position: tuple[int, int] | None) -> None:
    priority._tls.trace_page = None if page is None else int(page)
    priority._tls.trace_position = None if position is None else tuple(map(int, position))
    priority._tls.trace_row_call_index = 0


def _trace_call(record: dict) -> None:
    if float(record["elapsed"]) < _TRACE_SECONDS:
        return
    page = getattr(priority._tls, "trace_page", None)
    position = getattr(priority._tls, "trace_position", None)
    index = int(getattr(priority._tls, "trace_row_call_index", 0)) + 1
    priority._tls.trace_row_call_index = index
    where = ""
    if page is not None and position is not None:
        where = f" page {page} column {position[0]} row {position[1]}"
    print(
        "fast-call:" + where +
        f" call={index} elapsed={record['elapsed']:.3f}s"
        f" success={int(record['success'])}"
        f" states={record['states']}"
        f" memo_hits={record['memo_hits']}"
        f" placements={record['placements']}"
        f" max_depth={record['max_depth']}"
        f" state_limit={int(record['state_limit'])}",
        flush=True,
    )


def traced_page_cached_prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """The ordinary page-cached search plus observational recursive counters."""
    if not ink:
        return None

    started = perf_counter()
    page_candidates = _bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    stats = priority._stats()
    stats["calls"] += 1
    stats[f"{row_kind}_hints"] += 1

    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
    states = 0
    memo_hits = 0
    placements_tested = 0
    max_depth = 0
    hit_state_limit = False

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
        depth: int,
    ) -> tuple[Match, ...] | None:
        nonlocal states, memo_hits, placements_tested, max_depth, hit_state_limit
        if depth > max_depth:
            max_depth = depth
        if not remaining:
            return ()
        state = (remaining, baseline, leading_homonym_seen)
        if state in failed:
            memo_hits += 1
            return None
        states += 1
        if states > max_states:
            hit_state_limit = True
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)

        for model, min_x, left_pixels in _iter_candidates(
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
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
                if not placed.issubset(remaining):
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
                    depth + 1,
                )
                if tail is not None:
                    record_model_hit(model)
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None, None, False, 0)
    stats["placements_tested"] += placements_tested
    success = chosen is not None
    _trace_call(
        {
            "elapsed": perf_counter() - started,
            "success": success,
            "states": states,
            "memo_hits": memo_hits,
            "placements": placements_tested,
            "max_depth": max_depth,
            "state_limit": hit_state_limit,
        }
    )
    if chosen is None:
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
        baseline = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline = selected[0].baseline

    stats["successful_calls"] += 1
    return baseline, selected, placements_tested
