from __future__ import annotations

"""Benchmark safe x-islands with one deterministic permanent +1 baseline shift.

A blank x-run wider than every learned glyph's internal blank run proves that
no glyph can cross it. Such gaps split the row into combinatorially independent
islands, but baseline remains globally constrained:

* the first island establishes baseline B;
* later islands are tested on B from left to right;
* at the first island that cannot be solved exactly on B, B+1 is tried once;
* if B+1 succeeds, the downshift is locked and all remaining islands must use
  B+1;
* there is no upward shift and no second shift.

Every island must still cover its source ink exactly. If this strict model
cannot prove the row, the unchanged existing analyser remains authoritative.

The wrapper delegates to the monotonic-boundary benchmark, retaining live row
logging, regression comparison, and TOP 4 slow-row reporting.
"""

from collections import Counter
from dataclasses import replace
from time import perf_counter

from . import ocr_group_baseline_fallback as baseline_fallback
from . import ocr_monotonic_proof_boundary_benchmark as monotonic
from .ocr_glyph_gap_matcher import (
    _drop_partial_component_matches,
    exact_matches_by_safe_gaps,
    max_internal_blank_run,
    safe_ink_groups,
)
from .ocr_glyph_matcher import select_best_disjoint_exact_for_ink
from .ocr_probe_row_glyphs import row_ink


_STATS: Counter[str] = Counter()
_SLOW_ROWS: list[tuple[float, int, int | None, str]] = []


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
    """Return one complete exact solution at ``baseline`` or None.

    Candidate generation is still exact and unchanged. The important
    difference from the previous experiment is that we never enumerate all
    possible exact baselines for an island and never reconsider an island for
    multiple candidate switch points.
    """
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
    """Return exact first-island solutions keyed by baseline.

    Only the first island is allowed to establish B. This is the one place
    where multiple baselines may be considered. Subsequent islands are tested
    only at the single current baseline (B or, after the shift, B+1).
    """
    candidates, _bounds = exact_matches_by_safe_gaps(local_ink, width, height, models)
    by_baseline: dict[int, list] = {}
    for baseline in sorted({int(match.baseline) for match in candidates}):
        same = [match for match in candidates if int(match.baseline) == baseline]
        chosen = select_best_disjoint_exact_for_ink(same, local_ink)
        chosen = _drop_partial_component_matches(chosen, local_ink)
        if _covered(chosen) == local_ink:
            by_baseline[baseline] = chosen
    return by_baseline, len(candidates)


def _try_deterministic_plan(groups, crop_height: int, model_rows, base: int, first_selected):
    selected = [_shift_match(match, int(groups[0][0])) for match in first_selected]
    candidate_count = 0
    shifted = False
    switch_index: int | None = None

    for index, (left, right, local_ink) in enumerate(groups[1:], start=1):
        width = int(right) - int(left)
        wanted = int(base) + (1 if shifted else 0)
        local_selected, candidates = _exact_solution_at_baseline(
            local_ink, width, crop_height, model_rows, wanted
        )
        candidate_count += int(candidates)

        if local_selected is None and not shifted:
            # First failure at B is the only place a downshift can begin. Try
            # exactly B+1 once, then lock the state permanently on success.
            local_selected, candidates2 = _exact_solution_at_baseline(
                local_ink, width, crop_height, model_rows, int(base) + 1
            )
            candidate_count += int(candidates2)
            if local_selected is not None:
                shifted = True
                switch_index = index
                wanted = int(base) + 1

        if local_selected is None:
            return None, candidate_count, switch_index

        selected.extend(_shift_match(match, int(left)) for match in local_selected)

    return selected, candidate_count, switch_index


def _strict_single_downshift_analyser(crop, models, *, threshold: int = 210) -> dict:
    started = perf_counter()
    ink = row_ink(crop, threshold=threshold)
    model_rows = list(models)
    if not ink:
        return baseline_fallback._single_downshift_original(
            crop, model_rows, threshold=threshold
        )

    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    if not groups:
        return baseline_fallback._single_downshift_original(
            crop, model_rows, threshold=threshold
        )

    _STATS["calls"] += 1
    _STATS["islands"] += len(groups)
    _STATS["max_islands"] = max(_STATS["max_islands"], len(groups))

    first_left, first_right, first_ink = groups[0]
    first_solutions, first_candidates = _first_island_solutions(
        first_ink, int(first_right) - int(first_left), crop.height, model_rows
    )
    if not first_solutions:
        _STATS["fallback_rows"] += 1
        return baseline_fallback._single_downshift_original(
            crop, model_rows, threshold=threshold
        )

    chosen_plan = None
    candidate_count = int(first_candidates)
    for base, first_selected in first_solutions.items():
        plan, extra_candidates, switch_index = _try_deterministic_plan(
            groups, crop.height, model_rows, int(base), first_selected
        )
        candidate_count += int(extra_candidates)
        if plan is not None:
            chosen_plan = (int(base), switch_index, plan)
            break

    if chosen_plan is None:
        _STATS["fallback_rows"] += 1
        _STATS["strict_misses"] += 1
        return baseline_fallback._single_downshift_original(
            crop, model_rows, threshold=threshold
        )

    base, switch_index, selected = chosen_plan
    selected.sort(key=lambda match: (match.x, match.baseline, match.label, match.style))
    covered = _covered(selected)
    if covered != ink:
        _STATS["fallback_rows"] += 1
        return baseline_fallback._single_downshift_original(
            crop, model_rows, threshold=threshold
        )

    shifted = switch_index is not None
    _STATS["strict_exact_rows"] += 1
    _STATS["shifted_rows" if shifted else "unshifted_rows"] += 1
    elapsed = perf_counter() - started
    if elapsed >= 0.02:
        _SLOW_ROWS.append((elapsed, len(groups), switch_index, "shift" if shifted else "flat"))

    print(
        "single-downshift: "
        f"islands={len(groups)} base={base} "
        f"shift_after={'none' if switch_index is None else switch_index - 1} "
        f"next_baseline={'none' if switch_index is None else base + 1} "
        f"time={elapsed:.4f}s text={''.join(match.label for match in selected)!r}",
        flush=True,
    )

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
        "exact_cover_path": "single-downshift-safe-islands-deterministic",
        "baseline_segments": [
            {"left": 0, "right": crop.width, "baseline": base}
        ] if switch_index is None else [
            {"left": 0, "right": int(groups[switch_index][0]), "baseline": base},
            {"left": int(groups[switch_index][0]), "right": crop.width, "baseline": base + 1},
        ],
        "single_downshift_base": base,
        "single_downshift_switch_index": switch_index,
    }


def _print_stats() -> None:
    print(
        "single-downshift-summary: "
        f"calls={_STATS['calls']} strict_exact_rows={_STATS['strict_exact_rows']} "
        f"shifted_rows={_STATS['shifted_rows']} unshifted_rows={_STATS['unshifted_rows']} "
        f"strict_misses={_STATS['strict_misses']} fallback_rows={_STATS['fallback_rows']} "
        f"islands={_STATS['islands']} max_islands_per_row={_STATS['max_islands']}",
        flush=True,
    )
    if _SLOW_ROWS:
        print("slowest-single-downshift-rows: top=4", flush=True)
        for rank, (elapsed, islands, switch_index, mode) in enumerate(
            sorted(_SLOW_ROWS, reverse=True)[:4], start=1
        ):
            print(
                "slowest-single-downshift-row: "
                f"rank={rank} islands={islands} switch_index={switch_index} "
                f"mode={mode} time={elapsed:.3f}s",
                flush=True,
            )


def main() -> int:
    original = baseline_fallback.analyse_row_exact_grouped
    baseline_fallback._single_downshift_original = original
    baseline_fallback.analyse_row_exact_grouped = _strict_single_downshift_analyser
    try:
        result = monotonic.main()
    finally:
        baseline_fallback.analyse_row_exact_grouped = original
        if hasattr(baseline_fallback, "_single_downshift_original"):
            delattr(baseline_fallback, "_single_downshift_original")
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
