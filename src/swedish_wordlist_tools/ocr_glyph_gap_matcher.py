from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel, Match, exact_matches, select_best_disjoint_exact


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

    Returns ``(left, right_exclusive, local_ink)``.  ``local_ink`` has x=0 at
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


def exact_matches_by_safe_gaps(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
) -> tuple[list[Match], list[tuple[int, int]]]:
    """Generate exactly the same possible placements, but only inside safe groups."""
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    candidates: list[Match] = []
    bounds: list[tuple[int, int]] = []
    for left, right, local_ink in groups:
        group_width = right - left
        bounds.append((left, right))
        local = exact_matches(local_ink, group_width, height, model_rows)
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

    White gaps wider than every learned glyph's internal blank run prove that
    no exact placement can cross a group boundary.  For a fixed baseline the
    optimal disjoint cover is therefore the union of the optimal covers of the
    individual groups.
    """
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    if not groups:
        return None, [], [], []

    candidates_by_group: list[list[Match]] = []
    all_candidates: list[Match] = []
    bounds: list[tuple[int, int]] = []
    baselines: set[int] = set()
    for left, right, local_ink in groups:
        local = exact_matches(local_ink, right - left, height, model_rows)
        shifted = [_shift_match(match, left) for match in local]
        candidates_by_group.append(shifted)
        all_candidates.extend(shifted)
        bounds.append((left, right))
        baselines.update(match.baseline for match in shifted)

    best_baseline: int | None = None
    best_selected: list[Match] = []
    best_key: tuple[int, int, int, int] | None = None
    for baseline in sorted(baselines):
        selected: list[Match] = []
        for candidates in candidates_by_group:
            same_baseline = [match for match in candidates if match.baseline == baseline]
            if same_baseline:
                selected.extend(select_best_disjoint_exact(same_baseline, beam_width=beam_width))
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
