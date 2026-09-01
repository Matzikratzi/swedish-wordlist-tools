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


def _drop_partial_component_matches(
    selected: Iterable[Match],
    ink: set[tuple[int, int]],
) -> list[Match]:
    """Keep only matches whose touched 4-components are collectively complete.

    Temporary partial ownership is allowed while solving so two touching glyphs
    can form one exact partition. But the final answer must never recognize a
    glyph from only part of a source component (for example reading the dot of a
    semicolon as a period while leaving the semicolon's tail unmatched).
    """
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


def exact_matches_by_safe_gaps(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
) -> tuple[list[Match], list[tuple[int, int]]]:
    """Generate exact placements inside provably independent x-groups.

    Individual candidates may own only part of a 4-connected source component;
    the partition solver later requires collective ownership. This is what lets
    two printed glyphs that touch by an edge remain separate.
    """
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    candidates: list[Match] = []
    bounds: list[tuple[int, int]] = []
    for left, right, local_ink in groups:
        group_width = right - left
        bounds.append((left, right))
        local = exact_matches(
            local_ink,
            group_width,
            height,
            model_rows,
            require_whole_components=False,
        )
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
    exact placement can cross a group boundary. Within each group several glyphs
    may collectively own one touching source component, but the final selection
    may not leave a touched component only partly covered.
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
        local = exact_matches(
            local_ink,
            right - left,
            height,
            model_rows,
            require_whole_components=False,
        )
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
