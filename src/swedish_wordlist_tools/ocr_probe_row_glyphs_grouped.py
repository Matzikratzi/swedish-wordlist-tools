from __future__ import annotations

from .ocr_glyph_gap_matcher import select_best_baseline_partition_by_safe_gaps
from .ocr_probe_row_glyphs import ink_components, row_ink


def analyse_row_exact_grouped(crop, models, *, threshold: int = 210) -> dict:
    """Exact row analysis split only at provably uncrossable white x-runs."""
    ink = row_ink(crop, threshold=threshold)
    baseline, selected, candidates, groups = select_best_baseline_partition_by_safe_gaps(
        ink,
        crop.width,
        crop.height,
        models,
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
    }
