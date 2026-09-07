from __future__ import annotations

"""Conservative x-segmented exact-cover fast path.

A row may be split only across an x gap that is wider than the horizontal span
of every facit model.  No glyph can then cover ink on both sides of the gap.
For ordinary (non-homonym) rows, all glyphs in a valid exact cover share one
baseline, so each independent x segment can be solved separately for each
candidate baseline.  If the segmented probe cannot prove a full cover, the
unchanged page-cached search is used as fallback.
"""

from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_page_cached_fast_path import (
    _PageCandidates,
    _bound_page_candidates,
    _iter_candidates,
    page_cached_prioritized_fast_exact_cover as _unsplit_exact_cover,
)


def _all_prepared(candidates: _PageCandidates):
    for bucket in (
        candidates.homonym,
        candidates.bold,
        candidates.roman,
        candidates.italic,
        candidates.other,
    ):
        yield from bucket


def _max_model_x_span(candidates: _PageCandidates) -> int:
    span = 0
    for model, _min_x, _left_pixels in _all_prepared(candidates):
        xs = [x for x, _y in model.pixels]
        if xs:
            span = max(span, max(xs) - min(xs))
    return span


def safe_x_segments(
    ink: set[tuple[int, int]] | frozenset[tuple[int, int]],
    candidates: _PageCandidates,
) -> tuple[frozenset[tuple[int, int]], ...]:
    """Split only where no facit glyph can geometrically bridge the x gap."""
    occupied_x = sorted({x for x, _y in ink})
    if len(occupied_x) < 2:
        return (frozenset(ink),)

    max_span = _max_model_x_span(candidates)
    boundaries: list[int] = []
    for left, right in zip(occupied_x, occupied_x[1:]):
        if right - left > max_span:
            boundaries.append(left)
    if not boundaries:
        return (frozenset(ink),)

    segments: list[frozenset[tuple[int, int]]] = []
    remaining = set(ink)
    lower = min(occupied_x)
    for boundary in boundaries:
        part = frozenset((x, y) for x, y in remaining if lower <= x <= boundary)
        if part:
            segments.append(part)
            remaining.difference_update(part)
        lower = boundary + 1
    if remaining:
        segments.append(frozenset(remaining))
    return tuple(segments) if segments else (frozenset(ink),)


def _candidate_baselines(
    segment: frozenset[tuple[int, int]],
    width: int,
    height: int,
    candidates: _PageCandidates,
    row_kind: str,
) -> tuple[int, ...]:
    anchor_x = min(x for x, _y in segment)
    anchor_y = min(y for x, y in segment if x == anchor_x)
    out: list[int] = []
    seen: set[int] = set()
    for model, min_x, left_pixels in _iter_candidates(
        candidates,
        first_glyph=True,
        previous_style=None,
        row_kind=row_kind,
        leading_homonym_seen=False,
        baseline_established=False,
    ):
        x0 = anchor_x - min_x
        if x0 < 0 or x0 + model.width > width:
            continue
        for _mx, my in left_pixels:
            baseline = anchor_y - my
            if baseline in seen:
                continue
            if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                continue
            placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
            if placed.issubset(segment):
                seen.add(baseline)
                out.append(baseline)
    return tuple(out)


def _solve_segment(
    segment: frozenset[tuple[int, int]],
    *,
    baseline: int,
    width: int,
    height: int,
    candidates: _PageCandidates,
    row_kind: str,
    first_segment: bool,
    state_budget: list[int],
    max_states: int,
    placements: list[int],
) -> tuple[Match, ...] | None:
    failed: set[frozenset[tuple[int, int]]] = set()

    def search(
        remaining: frozenset[tuple[int, int]],
        previous_style: str | None,
    ) -> tuple[Match, ...] | None:
        if not remaining:
            return ()
        if remaining in failed:
            return None
        state_budget[0] += 1
        if state_budget[0] > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = first_segment and len(remaining) == len(segment)
        for model, min_x, left_pixels in _iter_candidates(
            candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=False,
            baseline_established=True,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                if candidate_baseline != baseline:
                    continue
                if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                    continue
                placements[0] += 1
                placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
                if not placed.issubset(remaining):
                    continue
                match = Match(
                    label=model.label,
                    style=model.style,
                    x=x0,
                    baseline=baseline,
                    pixels=placed,
                    model_pixels=len(model.pixels),
                    sources=model.sources,
                )
                tail = search(
                    frozenset(remaining.difference(placed)),
                    priority._typographic_style(model.style),
                )
                if tail is not None:
                    return (match,) + tail
        failed.add(remaining)
        return None

    return search(segment, None)


def segmented_page_cached_prioritized_fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Try safe x-segmented exact cover, otherwise use the unchanged search."""
    if not ink:
        return None

    candidates = _bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    if row_kind == "homonym":
        return _unsplit_exact_cover(ink, width, height, models, max_states=max_states)

    segments = safe_x_segments(ink, candidates)
    if len(segments) <= 1:
        return _unsplit_exact_cover(ink, width, height, models, max_states=max_states)

    probe_stats = priority._stats()
    probe_stats["segmented_probes"] = probe_stats.get("segmented_probes", 0) + 1
    probe_stats["segmented_parts"] = probe_stats.get("segmented_parts", 0) + len(segments)

    baselines = _candidate_baselines(segments[0], width, height, candidates, row_kind)
    for baseline in baselines:
        state_budget = [0]
        placements = [0]
        chosen: list[Match] = []
        solved = True
        for index, segment in enumerate(segments):
            part = _solve_segment(
                segment,
                baseline=baseline,
                width=width,
                height=height,
                candidates=candidates,
                row_kind=row_kind,
                first_segment=index == 0,
                state_budget=state_budget,
                max_states=max_states,
                placements=placements,
            )
            if part is None:
                solved = False
                break
            chosen.extend(part)
        if not solved:
            continue

        selected = sorted(
            chosen,
            key=lambda match: (match.x, match.baseline, match.label, str(match.style)),
        )
        if not selected:
            continue
        covered = set().union(*(match.pixels for match in selected))
        if covered != set(ink):
            continue

        stats = priority._stats()
        stats["calls"] += 1
        stats[f"{row_kind}_hints"] += 1
        stats["successful_calls"] += 1
        stats["placements_tested"] += placements[0]
        stats["segmented_success"] = stats.get("segmented_success", 0) + 1
        stats["segmented_states"] = stats.get("segmented_states", 0) + state_budget[0]
        for match in selected:
            # Popularity is observational. Match identity is enough here because
            # record_model_hit keys models by runtime identity; find the exact
            # selected model in the prepared candidates.
            for model, _min_x, _left_pixels in _all_prepared(candidates):
                if (
                    model.label == match.label
                    and model.style == match.style
                    and len(model.pixels) == match.model_pixels
                    and frozenset((match.x + x, baseline + y) for x, y in model.pixels)
                    == match.pixels
                ):
                    record_model_hit(model)
                    break
        return baseline, selected, placements[0]

    probe_stats["segmented_fallbacks"] = probe_stats.get("segmented_fallbacks", 0) + 1
    return _unsplit_exact_cover(ink, width, height, models, max_states=max_states)
