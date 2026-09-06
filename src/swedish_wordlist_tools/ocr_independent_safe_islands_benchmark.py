from __future__ import annotations

"""Benchmark solving provably independent horizontal ink islands separately.

A blank x-run wider than every learned glyph's internal blank run is a proof
that no glyph can cross that gap.  This experiment therefore solves every such
island independently and lets each island choose its own baseline.  Each island
tries the bounded fast exact-cover search first; only that island falls back to
safe exhaustive matching.  If any island still cannot be proved exact, the
unchanged row analyser remains the authoritative fallback.

The wrapper delegates to the monotonic-boundary benchmark, so execution-order
logging, regression comparison, and TOP 4 slow-row reporting remain available.
"""

from collections import Counter
from dataclasses import replace
from time import perf_counter

from . import ocr_group_baseline_fallback as baseline_fallback
from . import ocr_monotonic_proof_boundary_benchmark as monotonic
from .ocr_glyph_gap_matcher import (
    fast_exact_cover,
    max_internal_blank_run,
    safe_ink_groups,
    select_best_baseline_partition_by_safe_gaps,
)
from .ocr_probe_row_glyphs import row_ink


_STATS: Counter[str] = Counter()
_SLOW_ISLANDS: list[tuple[float, int, int, int, str]] = []


def _shift_match(match, dx: int):
    return replace(
        match,
        x=int(match.x) + int(dx),
        pixels=frozenset((int(x) + int(dx), int(y)) for x, y in match.pixels),
    )


def _covered(matches) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def _independent_island_analyser(crop, models, *, threshold: int = 210) -> dict:
    ink = row_ink(crop, threshold=threshold)
    model_rows = list(models)
    if not ink:
        return baseline_fallback.analyse_row_exact_grouped(
            crop, model_rows, threshold=threshold
        )

    internal_gap = max_internal_blank_run(model_rows)
    groups = safe_ink_groups(ink, max_internal_gap=internal_gap)
    _STATS["calls"] += 1
    _STATS["islands"] += len(groups)
    _STATS["max_islands"] = max(_STATS["max_islands"], len(groups))

    selected = []
    candidate_count = 0
    used_exhaustive = 0

    for group_index, (left, right, local_ink) in enumerate(groups):
        group_started = perf_counter()
        local_width = right - left
        path = "fast"

        fast = fast_exact_cover(
            local_ink,
            local_width,
            crop.height,
            model_rows,
        )
        if fast is not None:
            _baseline, local_selected, placements = fast
            candidate_count += int(placements)
            _STATS["fast_islands"] += 1
        else:
            path = "exhaustive"
            used_exhaustive += 1
            _STATS["exhaustive_islands"] += 1
            _baseline, local_selected, candidates, _local_groups = (
                select_best_baseline_partition_by_safe_gaps(
                    local_ink,
                    local_width,
                    crop.height,
                    model_rows,
                )
            )
            candidate_count += len(candidates)

        elapsed = perf_counter() - group_started
        if elapsed >= 0.02:
            _SLOW_ISLANDS.append(
                (elapsed, int(left), int(right), int(group_index), path)
            )

        if _covered(local_selected) != local_ink:
            _STATS["fallback_rows"] += 1
            return baseline_fallback.analyse_row_exact_grouped(
                crop, model_rows, threshold=threshold
            )

        selected.extend(_shift_match(match, left) for match in local_selected)

    selected.sort(key=lambda match: (match.x, match.baseline, match.label, match.style))
    covered = _covered(selected)
    if covered != ink:
        _STATS["fallback_rows"] += 1
        return baseline_fallback.analyse_row_exact_grouped(
            crop, model_rows, threshold=threshold
        )

    _STATS["island_exact_rows"] += 1
    if used_exhaustive:
        _STATS["mixed_rows"] += 1
    else:
        _STATS["all_fast_rows"] += 1

    baselines = sorted({int(match.baseline) for match in selected})
    return {
        "baseline": int(selected[0].baseline) if selected else None,
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
        "exact_fast_path": used_exhaustive == 0,
        "exact_cover_path": (
            "independent-safe-islands-fast"
            if used_exhaustive == 0
            else "independent-safe-islands-mixed"
        ),
        "island_baselines": baselines,
    }


def _print_stats() -> None:
    print(
        "independent-islands-summary: "
        f"calls={_STATS['calls']} island_exact_rows={_STATS['island_exact_rows']} "
        f"all_fast_rows={_STATS['all_fast_rows']} mixed_rows={_STATS['mixed_rows']} "
        f"fallback_rows={_STATS['fallback_rows']} islands={_STATS['islands']} "
        f"fast_islands={_STATS['fast_islands']} exhaustive_islands={_STATS['exhaustive_islands']} "
        f"max_islands_per_row={_STATS['max_islands']}",
        flush=True,
    )
    if _SLOW_ISLANDS:
        print("slowest-islands: top=4", flush=True)
        for rank, (elapsed, left, right, group_index, path) in enumerate(
            sorted(_SLOW_ISLANDS, reverse=True)[:4], start=1
        ):
            print(
                "slowest-island: "
                f"rank={rank} group={group_index} x={left}..{right} "
                f"width={right-left} time={elapsed:.3f}s path={path}",
                flush=True,
            )


def main() -> int:
    original = baseline_fallback.analyse_row_exact_grouped
    baseline_fallback.analyse_row_exact_grouped = _independent_island_analyser
    try:
        result = monotonic.main()
    finally:
        baseline_fallback.analyse_row_exact_grouped = original
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
