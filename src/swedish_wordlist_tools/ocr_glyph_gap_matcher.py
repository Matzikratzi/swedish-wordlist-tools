from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .ocr_glyph_matcher import (
    GlyphModel,
    Match,
    _ink_components,
    exact_matches,
    select_best_disjoint_exact_for_ink,
)


def max_internal_blank_run(models: Iterable[GlyphModel]) -> int:
    """Largest wholly blank x-column run inside any learned glyph bounding box.

    A source-row blank run wider than this cannot be crossed by any known glyph,
    so it is a provably safe place to split exact matching into independent
    horizontal groups.
    """
    largest = 0
    for model in models:
        occupied = {x for x, _y in model.pixels}
        if not occupied:
            continue
        left = min(occupied)
        right = max(occupied)
        current = 0
        for x in range(left, right + 1):
            if x in occupied:
                current = 0
            else:
                current += 1
                largest = max(largest, current)
    return largest


def safe_ink_groups(
    ink: set[tuple[int, int]],
    *,
    max_internal_gap: int,
) -> list[tuple[int, int, set[tuple[int, int]]]]:
    """Split source ink at blank-column runs no known glyph can cross.

    Returns ``(left, right_exclusive, local_ink)``. ``local_ink`` has x=0 at
    ``left`` so exact matching can run in the smallest possible horizontal box.
    """
    if not ink:
        return []
    occupied = sorted({x for x, _y in ink})
    groups: list[tuple[int, int]] = []
    start = occupied[0]
    previous = occupied[0]
    for x in occupied[1:]:
        blank_run = x - previous - 1
        if blank_run > max_internal_gap:
            groups.append((start, previous + 1))
            start = x
        previous = x
    groups.append((start, previous + 1))

    out: list[tuple[int, int, set[tuple[int, int]]]] = []
    for left, right in groups:
        local = {(x - left, y) for x, y in ink if left <= x < right}
        out.append((left, right, local))
    return out


def _shift_match(match: Match, dx: int) -> Match:
    return replace(
        match,
        x=match.x + dx,
        pixels=frozenset((x + dx, y) for x, y in match.pixels),
    )


def fast_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> tuple[int, list[Match], int] | None:
    """Find a complete exact cover without sliding every model across the row.

    The leftmost uncovered source pixel proves the horizontal placement of the
    next glyph: a disjoint exact cover cannot contain a new glyph with ink to
    its left.  We therefore anchor each candidate model's leftmost ink column
    at that x coordinate and only try baselines implied by pixels in that model
    column.  Internal blank columns (for example in a bold ``k``) are irrelevant
    and remain fully supported.

    This is deliberately only a fast *success* path.  It returns a result only
    when every source pixel is covered exactly by non-overlapping learned glyphs
    on one baseline.  If search becomes ambiguous/large, or a piecewise baseline
    is needed, the caller falls back to the existing exhaustive matcher.
    """
    if not ink:
        return None

    model_rows = [model for model in models if model.pixels]
    prepared: list[tuple[GlyphModel, int, tuple[tuple[int, int], ...]]] = []
    for model in model_rows:
        min_x = min(x for x, _y in model.pixels)
        left_pixels = tuple(sorted((x, y) for x, y in model.pixels if x == min_x))
        prepared.append((model, min_x, left_pixels))

    # Prefer strong, information-rich models first so ordinary exact rows finish
    # without exploring alternative partitions.  The exhaustive fallback remains
    # authoritative whenever this bounded search does not find a complete cover.
    prepared.sort(
        key=lambda row: (
            -len(row[0].pixels),
            -int(row[0].sources),
            row[0].label,
            row[0].style,
        )
    )

    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested
        if not remaining:
            return ()
        state = (remaining, baseline)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)

        for model, min_x, left_pixels in prepared:
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
                    (x0 + x, candidate_baseline + y)
                    for x, y in model.pixels
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
                tail = search(
                    frozenset(remaining.difference(placed)),
                    candidate_baseline if baseline is None else baseline,
                )
                if tail is not None:
                    return (match,) + tail

        failed.add(state)
        return None

    chosen = search(target, None)
    if chosen is None:
        return None
    selected = sorted(chosen, key=lambda match: (match.x, match.baseline, match.label, match.style))
    baseline = selected[0].baseline
    return baseline, selected, placements_tested


def _drop_partial_component_matches(
    selected: Iterable[Match],
    ink: set[tuple[int, int]],
) -> list[Match]:
    """Keep only matches whose touched 4-components are collectively complete."""
    kept = list(selected)
    components, _by_pixel = _ink_components(ink)
    while kept:
        occupied = frozenset().union(*(match.pixels for match in kept))
        incomplete = [
            component
            for component in components
            if component.intersection(occupied) and not component.issubset(occupied)
        ]
        if not incomplete:
            break
        bad_pixels = frozenset().union(*incomplete)
        new_kept = [match for match in kept if match.pixels.isdisjoint(bad_pixels)]
        if len(new_kept) == len(kept):
            break
        kept = new_kept
    return sorted(kept, key=lambda match: (match.x, match.baseline, match.label, match.style))


def _component_aware_candidates(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: list[GlyphModel],
) -> list[Match]:
    """Use cheap strict candidates except where touching glyphs require a split.

    A strict exact match owns every 4-connected source component it touches.
    Therefore partial-component candidates are useful only for source components
    which no strict glyph can own at all, such as an edge-touching ``t;`` pair.
    Restricting the expensive permissive search to those unresolved components
    preserves touching-glyph support without multiplying candidates everywhere.
    """
    strict = exact_matches(
        ink,
        width,
        height,
        models,
        require_whole_components=True,
    )
    components, by_pixel = _ink_components(ink)
    resolved_components: set[int] = set()
    for match in strict:
        resolved_components.update(by_pixel[pixel] for pixel in match.pixels)
    unresolved_components = set(range(len(components))) - resolved_components
    if not unresolved_components:
        return strict

    permissive = exact_matches(
        ink,
        width,
        height,
        models,
        require_whole_components=False,
    )
    partial = [
        match
        for match in permissive
        if any(by_pixel[pixel] in unresolved_components for pixel in match.pixels)
    ]

    # Preserve deterministic order while avoiding duplicate strict/permissive placements.
    seen = {
        (match.label, match.style, match.x, match.baseline, match.pixels)
        for match in strict
    }
    out = list(strict)
    for match in partial:
        key = (match.label, match.style, match.x, match.baseline, match.pixels)
        if key not in seen:
            seen.add(key)
            out.append(match)
    return out


def exact_matches_by_safe_gaps(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
) -> tuple[list[Match], list[tuple[int, int]]]:
    """Generate exact placements inside provably independent x-groups."""
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    candidates: list[Match] = []
    bounds: list[tuple[int, int]] = []
    for left, right, local_ink in groups:
        group_width = right - left
        bounds.append((left, right))
        local = _component_aware_candidates(local_ink, group_width, height, model_rows)
        candidates.extend(_shift_match(match, left) for match in local)
    return candidates, bounds


def select_best_baseline_partition_by_safe_gaps(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    beam_width: int = 512,
) -> tuple[int | None, list[Match], list[Match], list[tuple[int, int]]]:
    """Choose one baseline while solving independent safe groups separately.

    White gaps wider than every learned glyph's internal blank run prove that no
    exact placement can cross a group boundary. Strict whole-component matching
    is used by default; permissive partitioning is generated only for components
    that have no strict glyph candidate and may therefore contain touching glyphs.
    """
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    if not groups:
        return None, [], [], []

    candidates_by_group: list[list[Match]] = []
    local_inks: list[set[tuple[int, int]]] = []
    all_candidates: list[Match] = []
    bounds: list[tuple[int, int]] = []
    baselines: set[int] = set()
    for left, right, local_ink in groups:
        local = _component_aware_candidates(local_ink, right - left, height, model_rows)
        shifted = [_shift_match(match, left) for match in local]
        candidates_by_group.append(shifted)
        local_inks.append({(x + left, y) for x, y in local_ink})
        all_candidates.extend(shifted)
        bounds.append((left, right))
        baselines.update(match.baseline for match in shifted)

    best_baseline: int | None = None
    best_selected: list[Match] = []
    best_key: tuple[int, int, int, int] | None = None
    for baseline in sorted(baselines):
        selected: list[Match] = []
        for candidates, group_ink in zip(candidates_by_group, local_inks):
            same_baseline = [match for match in candidates if match.baseline == baseline]
            if same_baseline:
                group_selected = select_best_disjoint_exact_for_ink(
                    same_baseline,
                    group_ink,
                    beam_width=beam_width,
                )
                selected.extend(_drop_partial_component_matches(group_selected, group_ink))
        key = (
            sum(match.model_pixels for match in selected),
            sum(match.model_pixels * match.model_pixels for match in selected),
            sum(match.sources for match in selected),
            -len(selected),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_baseline = baseline
            best_selected = selected

    best_selected.sort(key=lambda match: (match.x, match.baseline, match.label, match.style))
    return best_baseline, best_selected, all_candidates, bounds
