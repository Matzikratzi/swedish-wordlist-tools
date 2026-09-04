from __future__ import annotations

from .ocr_glyph_gap_matcher import (
    fast_exact_cover,
    max_internal_blank_run,
    safe_ink_groups,
    select_best_baseline_partition_by_safe_gaps,
)
from .ocr_probe_row_glyphs import ink_components, row_ink


def analyse_row_exact_grouped(crop, models, *, threshold: int = 210) -> dict:
    """Exact row analysis with a bounded anchored fast path and safe fallback."""
    ink = row_ink(crop, threshold=threshold)
    model_rows = list(models)

    fast = fast_exact_cover(
        ink,
        crop.width,
        crop.height,
        model_rows,
    )
    if fast is not None:
        baseline, selected, placements_tested = fast
        internal_gap = max_internal_blank_run(model_rows)
        grouped = safe_ink_groups(ink, max_internal_gap=internal_gap)
        groups = [(left, right) for left, right, _local in grouped]
        covered = set().union(*(match.pixels for match in selected)) if selected else set()
        return {
            "baseline": baseline,
            "source_pixels": len(ink),
            "covered_pixels": len(covered),
            "unmatched_pixels": 0,
            "unmatched_components": [],
            "fully_exact": bool(ink) and covered == ink,
            "candidate_count": placements_tested,
            "selected": selected,
            "ink": ink,
            "safe_groups": groups,
            "safe_group_count": len(groups),
            "exact_fast_path": True,
        }

    baseline, selected, candidates, groups = select_best_baseline_partition_by_safe_gaps(
        ink,
        crop.width,
        crop.height,
        model_rows,
    )
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    unmatched = ink - covered
    return {
        "baseline": baseline,
        "source_pixels": len(ink),
        "covered_pixels": len(covered),
        "unmatched_pixels": len(unmatched),
        "unmatched_components": ink_components(unmatched),
        "fully_exact": bool(ink) and covered == ink,
        "candidate_count": len(candidates),
        "selected": selected,
        "ink": ink,
        "safe_groups": groups,
        "safe_group_count": len(groups),
        "exact_fast_path": False,
    }
