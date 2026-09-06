from __future__ import annotations

"""Benchmark monotonic row proof during bounded boundary repair.

Experimental policy only:

* if a candidate separator makes the complete upper row exact, keep that
  ownership immediately; the lower row may remain unresolved for its own pass;
* otherwise, if at least PROVEN_PREFIX_WIDTH source x-columns from the first
  ink column are exactly explained on/above the proposed baseline, keep only
  candidate ownership changes that are themselves covered by those proven
  prefix matches and restore the rest.

The final OCR matcher remains exact.  This wrapper delegates to the live row
trace benchmark so execution-order diagnostics and TOP 4 reporting remain
available.
"""

from collections import Counter
from time import perf_counter

from . import ocr_fast_regression_scan as fast_scan
from . import ocr_fast_boundary_repair as repair_mod
from . import ocr_live_row_trace_benchmark as live_trace
from . import ocr_split_facit_benchmark as split_benchmark
from .ocr_glyph_gap_matcher import max_internal_blank_run
from .ocr_pair_separator import (
    apply_cut_bidirectional,
    candidate_separator_tiers,
)


PROVEN_PREFIX_WIDTH = 30
_STATS: Counter[str] = Counter()


def _proven_prefix(state: dict, width: int = PROVEN_PREFIX_WIDTH) -> dict | None:
    """Return exact on/above-baseline prefix evidence, if at least ``width`` x-columns long."""
    baseline = state.get("baseline")
    ink = {(int(x), int(y)) for x, y in state.get("source_ink_points") or []}
    matches = list(state.get("matches") or [])
    if baseline is None or not ink or not matches:
        return None

    first_x = min(x for x, _y in ink)
    right = first_x + int(width)
    relevant = {(x, y) for x, y in ink if first_x <= x < right and y <= int(baseline)}
    if not relevant:
        return None

    covered: set[tuple[int, int]] = set()
    labels: list[str] = []
    for match in matches:
        points = {(int(x), int(y)) for x, y in match.pixels}
        if points.intersection(relevant):
            covered.update(points)
            labels.append(str(match.label))

    if not relevant.issubset(covered):
        return None

    # The requested span is measured in vertical pixel columns from the first
    # source ink column.  It need not itself contain ink in every column.
    crop_width = int(state.get("crop_width") or 0)
    if right > crop_width:
        return None

    return {
        "first_x": first_x,
        "right": right,
        "baseline": int(baseline),
        "relevant": relevant,
        "covered": covered,
        "labels": "".join(labels),
    }


def _restore_except(owners, changed, protected_offsets: set[int]) -> int:
    kept = 0
    for offset, old in reversed(changed):
        if int(offset) in protected_offsets:
            kept += 1
            continue
        owners.data[offset] = old
    return kept


def _monotonic_boundary_repair(
    context: dict,
    position: tuple[int, int],
    models,
    *,
    radius: int = 6,
):
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []
    if row_index + 1 >= len(rows):
        return repair_mod.FastBoundaryRepair(False, None, 0, 0, 0.0, None)

    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    boundary = int(rows[row_index]["page_bottom"])
    left, right = repair_mod._column_span(context, column)
    started = perf_counter()
    attempts = 0
    monotonically_kept = 0

    for strategy, cuts in candidate_separator_tiers(
        owners,
        upper_code=upper_code,
        lower_code=lower_code,
        boundary=boundary,
        left=left,
        right=right,
        radius=radius,
    ):
        for cut_y in cuts:
            changed = apply_cut_bidirectional(
                owners,
                upper_code=upper_code,
                lower_code=lower_code,
                cut_y=cut_y,
                boundary=boundary,
                left=left,
                right=right,
                radius=radius,
            )
            if not changed:
                continue

            attempts += 1
            upper = repair_mod._analyse_fast(context, position, models)

            if upper.get("fully_exact"):
                _STATS["whole_rows_kept"] += 1
                _STATS["whole_row_pixels_changed"] += len(changed)
                print(
                    "monotonic-proof: "
                    f"page={context['page_number']} column={column} row={row_index} "
                    f"kind=whole-row cut_y={cut_y} strategy={strategy} "
                    f"changed={len(changed)} attempts={attempts} "
                    f"baseline={upper.get('baseline')} text={upper.get('text', '')!r}",
                    flush=True,
                )
                return repair_mod.FastBoundaryRepair(
                    True,
                    cut_y,
                    len(changed) + monotonically_kept,
                    attempts,
                    perf_counter() - started,
                    f"{strategy}+monotonic-upper-exact",
                )

            proof = _proven_prefix(upper)
            protected_offsets: set[int] = set()
            if proof is not None:
                crop_left, crop_top, _crop_right, _crop_bottom = map(int, upper["crop_box"])
                for x, y in proof["relevant"]:
                    page_x = crop_left + int(x)
                    page_y = crop_top + int(y)
                    offset = page_y * owners.width + page_x
                    # Keep only ownership changes that now assign a genuinely
                    # matched/proven source pixel to this upper row.
                    if owners.data[offset] == upper_code:
                        protected_offsets.add(offset)

            kept = _restore_except(owners, changed, protected_offsets)
            if kept:
                monotonically_kept += kept
                _STATS["prefix_events"] += 1
                _STATS["prefix_pixels_kept"] += kept
                print(
                    "monotonic-proof: "
                    f"page={context['page_number']} column={column} row={row_index} "
                    f"kind=prefix width={PROVEN_PREFIX_WIDTH} "
                    f"x={proof['first_x']}..{proof['right']} baseline={proof['baseline']} "
                    f"kept_changed_pixels={kept} labels={proof['labels']!r} "
                    f"cut_y={cut_y} strategy={strategy}",
                    flush=True,
                )

    return repair_mod.FastBoundaryRepair(
        False,
        None,
        monotonically_kept,
        attempts,
        perf_counter() - started,
        "monotonic-prefix" if monotonically_kept else None,
    )


def _install_gap_reporter():
    original = split_benchmark.load_split_facit_with_typography

    def load_and_report(directory):
        models = original(directory)
        internal = max_internal_blank_run(models)
        print(
            "safe-gap-rule: "
            f"models={len(models)} max_internal_blank_run={internal} "
            f"split_requires_blank_run>{internal} "
            f"minimum_safe_blank_run={internal + 1}",
            flush=True,
        )
        return models

    split_benchmark.load_split_facit_with_typography = load_and_report
    return original


def _print_stats() -> None:
    print(
        "monotonic-proof-summary: "
        f"prefix_width={PROVEN_PREFIX_WIDTH} "
        f"whole_rows_kept={_STATS['whole_rows_kept']} "
        f"whole_row_pixels_changed={_STATS['whole_row_pixels_changed']} "
        f"prefix_events={_STATS['prefix_events']} "
        f"prefix_pixels_kept={_STATS['prefix_pixels_kept']}",
        flush=True,
    )


def main() -> int:
    original_repair = fast_scan.try_fast_boundary_repair
    original_loader = _install_gap_reporter()
    fast_scan.try_fast_boundary_repair = _monotonic_boundary_repair
    try:
        result = live_trace.main()
    finally:
        fast_scan.try_fast_boundary_repair = original_repair
        split_benchmark.load_split_facit_with_typography = original_loader
    _print_stats()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
