from __future__ import annotations

"""Install the deterministic one-time baseline downshift in the shared row parser.

The ordinary prioritized exact cover deliberately keeps one baseline for a
whole row.  Some SAOL rows contain one permanent one-pixel downward shift after
a provably safe white x-gap.  This module adds that strict fallback to the
shared analyser used by editor, scanner and regression benchmark:

* the first safe x-island establishes B;
* later islands must solve exactly at B;
* at the first failure, B+1 may be tried once;
* after a successful shift, every remaining island must stay at B+1;
* no upward shift and no second shift are allowed.

Every island must still be covered exactly by known facit glyphs.
"""

from dataclasses import replace

from .ocr_glyph_gap_matcher import (
    _drop_partial_component_matches,
    exact_matches_by_safe_gaps,
    max_internal_blank_run,
    safe_ink_groups,
)
from .ocr_glyph_matcher import select_best_disjoint_exact_for_ink


_installed = False


def _covered(matches) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def _shift_match(match, dx: int):
    return replace(
        match,
        x=int(match.x) + int(dx),
        pixels=frozenset((int(x) + int(dx), int(y)) for x, y in match.pixels),
    )


def _exact_solution_at_baseline(local_ink, width: int, height: int, models, baseline: int):
    candidates, _bounds = exact_matches_by_safe_gaps(local_ink, width, height, models)
    same = [match for match in candidates if int(match.baseline) == int(baseline)]
    if not same:
        return None, len(candidates)
    chosen = select_best_disjoint_exact_for_ink(same, local_ink)
    chosen = _drop_partial_component_matches(chosen, local_ink)
    if _covered(chosen) != local_ink:
        return None, len(candidates)
    return chosen, len(candidates)


def _first_island_solutions(local_ink, width: int, height: int, models):
    candidates, _bounds = exact_matches_by_safe_gaps(local_ink, width, height, models)
    by_baseline: dict[int, list] = {}
    for baseline in sorted({int(match.baseline) for match in candidates}):
        same = [match for match in candidates if int(match.baseline) == baseline]
        chosen = select_best_disjoint_exact_for_ink(same, local_ink)
        chosen = _drop_partial_component_matches(chosen, local_ink)
        if _covered(chosen) == local_ink:
            by_baseline[baseline] = chosen
    return by_baseline, len(candidates)


def _try_plan(groups, height: int, models, base: int, first_selected):
    selected = [_shift_match(match, int(groups[0][0])) for match in first_selected]
    candidate_count = 0
    shifted = False
    switch_index: int | None = None

    for index, (left, right, local_ink) in enumerate(groups[1:], start=1):
        width = int(right) - int(left)
        wanted = int(base) + (1 if shifted else 0)
        local_selected, candidates = _exact_solution_at_baseline(
            local_ink, width, height, models, wanted
        )
        candidate_count += int(candidates)

        if local_selected is None and not shifted:
            local_selected, candidates2 = _exact_solution_at_baseline(
                local_ink, width, height, models, int(base) + 1
            )
            candidate_count += int(candidates2)
            if local_selected is not None:
                shifted = True
                switch_index = index

        if local_selected is None:
            return None, candidate_count, switch_index

        selected.extend(_shift_match(match, int(left)) for match in local_selected)

    return selected, candidate_count, switch_index


def exact_single_downshift_result(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models,
) -> dict | None:
    """Return a strict exact B->B+1 solution, or ``None`` if it cannot be proven."""
    if not ink:
        return None

    model_rows = models if hasattr(models, "__len__") else tuple(models)
    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    if not groups:
        return None

    first_left, first_right, first_ink = groups[0]
    first_solutions, first_candidates = _first_island_solutions(
        first_ink, int(first_right) - int(first_left), height, model_rows
    )
    if not first_solutions:
        return None

    candidate_count = int(first_candidates)
    chosen_plan = None
    for base, first_selected in first_solutions.items():
        plan, extra_candidates, switch_index = _try_plan(
            groups, height, model_rows, int(base), first_selected
        )
        candidate_count += int(extra_candidates)
        if plan is not None:
            chosen_plan = (int(base), switch_index, plan)
            break

    if chosen_plan is None:
        return None

    base, switch_index, selected = chosen_plan
    selected.sort(key=lambda match: (match.x, match.baseline, match.label, str(match.style)))
    covered = _covered(selected)
    if covered != ink:
        return None

    return {
        "baseline": base,
        "source_pixels": len(ink),
        "covered_pixels": len(covered),
        "unmatched_pixels": 0,
        "unmatched_components": [],
        "fully_exact": True,
        "candidate_count": candidate_count,
        "selected": selected,
        "ink": ink,
        "safe_groups": [(int(left), int(right)) for left, right, _local in groups],
        "safe_group_count": len(groups),
        "exact_fast_path": False,
        "exact_cover_path": "shared-single-downshift-safe-islands",
        "baseline_segments": (
            [{"left": 0, "right": width, "baseline": base}]
            if switch_index is None
            else [
                {"left": 0, "right": int(groups[switch_index][0]), "baseline": base},
                {"left": int(groups[switch_index][0]), "right": width, "baseline": base + 1},
            ]
        ),
        "single_downshift_base": base,
        "single_downshift_switch_index": switch_index,
    }


def install_shared_single_downshift() -> None:
    """Wrap the one shared analyser before editor/batch import it by value."""
    global _installed
    if _installed:
        return

    from . import ocr_page_cached_fast_path as shared

    original = shared.analyse_row_prioritized
    if getattr(original, "_shared_single_downshift", False):
        _installed = True
        return

    def analyse_row_with_single_downshift(
        crop,
        models,
        *,
        threshold: int = 210,
        exact_cover=None,
    ) -> dict:
        result = original(crop, models, threshold=threshold, exact_cover=exact_cover)
        if result.get("fully_exact") or not result.get("ink"):
            return result
        fallback = exact_single_downshift_result(
            set(result["ink"]), crop.width, crop.height, models
        )
        return fallback if fallback is not None else result

    analyse_row_with_single_downshift._shared_single_downshift = True
    analyse_row_with_single_downshift._single_downshift_original = original
    shared.analyse_row_prioritized = analyse_row_with_single_downshift
    _installed = True
