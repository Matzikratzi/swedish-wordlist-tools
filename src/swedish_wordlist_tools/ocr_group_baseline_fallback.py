from __future__ import annotations

from typing import Iterable

from .ocr_glyph_gap_matcher import (
    _drop_partial_component_matches,
    exact_matches_by_safe_gaps,
)
from .ocr_glyph_matcher import GlyphModel, Match, select_best_disjoint_exact_for_ink
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


def _covered(matches: Iterable[Match]) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def analyse_row_exact_grouped_with_baseline_fallback(
    crop,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> dict:
    """Keep one row baseline, but rescue wholly failing later whitespace groups at ±1.

    The ordinary grouped matcher remains authoritative.  Only after it has chosen
    one baseline for the complete physical row do we inspect later safe-whitespace
    groups which remain incomplete.  Such a group may move by one pixel only if
    the alternate baseline explains the *entire* group's source ink exactly and
    does so with at least two glyphs.  This is deliberately a fallback for local
    typesetting shifts, not a general per-word baseline optimiser.
    """
    model_rows = list(models)
    result = analyse_row_exact_grouped(crop, model_rows, threshold=threshold)
    main_baseline = result.get("baseline")
    groups = list(result.get("safe_groups") or [])
    if main_baseline is None or len(groups) < 2 or result.get("fully_exact"):
        result["baseline_fallbacks"] = []
        return result

    candidates, bounds = exact_matches_by_safe_gaps(
        result["ink"], crop.width, crop.height, model_rows
    )
    if bounds != groups:
        groups = bounds

    selected = list(result["selected"])
    fallbacks: list[dict] = []

    for group_index, (left, right) in enumerate(groups):
        if group_index == 0:
            continue
        group_ink = {(x, y) for x, y in result["ink"] if left <= x < right}
        if not group_ink:
            continue
        existing = [m for m in selected if left <= m.x < right]
        if _covered(existing) == group_ink:
            continue

        best = None
        for delta in (-1, 1):
            baseline = int(main_baseline) + delta
            same = [m for m in candidates if left <= m.x < right and m.baseline == baseline]
            if not same:
                continue
            chosen = select_best_disjoint_exact_for_ink(same, group_ink)
            chosen = _drop_partial_component_matches(chosen, group_ink)
            covered = _covered(chosen)
            if covered != group_ink or len(chosen) < 2:
                continue
            key = (
                sum(m.model_pixels for m in chosen),
                sum(m.model_pixels * m.model_pixels for m in chosen),
                sum(m.sources for m in chosen),
                -len(chosen),
                -abs(delta),
            )
            if best is None or key > best[0]:
                best = (key, delta, chosen)

        if best is None:
            continue

        _key, delta, chosen = best
        selected = [m for m in selected if not (left <= m.x < right)] + list(chosen)
        fallbacks.append(
            {
                "group": group_index,
                "left": left,
                "right": right,
                "from_baseline": int(main_baseline),
                "to_baseline": int(main_baseline) + int(delta),
                "delta": int(delta),
                "labels": "".join(m.label for m in sorted(chosen, key=lambda m: m.x)),
                "pixels": len(group_ink),
                "status": "full-exact-whitespace-fallback",
            }
        )

    selected.sort(key=lambda m: (m.x, m.baseline, m.label, m.style))
    covered = _covered(selected)
    unmatched = result["ink"] - covered
    result["selected"] = selected
    result["covered_pixels"] = len(covered)
    result["unmatched_pixels"] = len(unmatched)
    result["fully_exact"] = bool(result["ink"]) and covered == result["ink"]
    result["baseline_fallbacks"] = fallbacks
    return result
