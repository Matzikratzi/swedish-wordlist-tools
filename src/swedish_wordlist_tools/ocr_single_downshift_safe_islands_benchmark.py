from __future__ import annotations

"""Benchmark safe x-islands with at most one permanent +1 baseline shift.

A blank x-run wider than every learned glyph's internal blank run proves that
no glyph can cross it.  Such gaps may split the row into combinatorially
independent islands, but they do *not* make baseline arbitrary:

* the first island establishes baseline B;
* every later island must use B, until optionally one gap performs B -> B+1;
* after that single downshift, every remaining island must stay on B+1.

There is no upward shift and no second shift.  Every island is still required
to cover its source ink exactly.  If this strict model cannot prove the row,
the unchanged existing analyser remains authoritative.

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
_SLOW_ROWS: list[tuple[float, int, int, str]] = []


def _covered(matches) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def _shift_match(match, dx: int):
    return replace(
        match,
        x=int(match.x) + int(dx),
        pixels=frozenset((int(x) + int(dx), int(y)) for x, y in match.pixels),
    )


def _exact_solutions_by_baseline(local_ink, width: int, height: int, models):
    """Return every baseline that has a complete exact solution for one island."""
    candidates, _bounds = exact_matches_by_safe_gaps(local_ink, width, height, models)
    by_baseline: dict[int, list] = {}
    baselines = sorted({int(match.baseline) for match in candidates})
    for baseline in baselines:
        same = [match for match in candidates if int(match.baseline) == baseline]
        if not same:
            continue
        chosen = select_best_disjoint_exact_for_ink(same, local_ink)
        chosen = _drop_partial_component_matches(chosen, local_ink)
        if _covered(chosen) == local_ink:
            by_baseline[baseline] = chosen
    return by_baseline, len(candidates)


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

    island_solutions = []
    candidate_count = 0
    for left, right, local_ink in groups:
        solutions, candidates = _exact_solutions_by_baseline(
            local_ink, int(right) - int(left), crop.height, model_rows
        )
        candidate_count += int(candidates)
        if not solutions:
            _STATS["fallback_rows"] += 1
            return baseline_fallback._single_downshift_original(
                crop, model_rows, threshold=threshold
            )
        island_solutions.append((int(left), int(right), local_ink, solutions))

    # First island establishes B.  A shift may happen only after an island,
    # hence switch_index is in 1..N-1; N means no shift at all.
    first_solutions = island_solutions[0][3]
    chosen_plan = None
    for base in sorted(first_solutions):
        for switch_index in range(len(island_solutions), 0, -1):
            selected = []
            ok = True
            for index, (left, _right, _local_ink, solutions) in enumerate(island_solutions):
                wanted = int(base) if index < switch_index else int(base) + 1
                local_selected = solutions.get(wanted)
                if local_selected is None:
                    ok = False
                    break
                selected.extend(_shift_match(match, left) for match in local_selected)
            if ok:
                chosen_plan = (int(base), int(switch_index), selected)
                break
        if chosen_plan is not None:
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

    shifted = switch_index < len(island_solutions)
    _STATS["strict_exact_rows"] += 1
    _STATS["shifted_rows" if shifted else "unshifted_rows"] += 1
    elapsed = perf_counter() - started
    if elapsed >= 0.02:
        _SLOW_ROWS.append((elapsed, len(groups), switch_index, "shift" if shifted else "flat"))

    print(
        "single-downshift: "
        f"islands={len(groups)} base={base} "
        f"shift_after={'none' if not shifted else switch_index - 1} "
        f"next_baseline={'none' if not shifted else base + 1} "
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
        "exact_cover_path": "single-downshift-safe-islands",
        "baseline_segments": [
            {"left": 0, "right": crop.width, "baseline": base}
        ] if not shifted else [
            {"left": 0, "right": island_solutions[switch_index][0], "baseline": base},
            {"left": island_solutions[switch_index][0], "right": crop.width, "baseline": base + 1},
        ],
        "single_downshift_base": base,
        "single_downshift_switch_index": None if not shifted else switch_index,
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
