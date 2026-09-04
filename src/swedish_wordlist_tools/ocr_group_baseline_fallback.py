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


def _exact_group_at_baseline(
    candidates: Iterable[Match],
    group_ink: set[tuple[int, int]],
    *,
    left: int,
    right: int,
    baseline: int,
) -> list[Match]:
    same = [m for m in candidates if left <= m.x < right and m.baseline == baseline]
    if not same:
        return []
    chosen = select_best_disjoint_exact_for_ink(same, group_ink)
    chosen = _drop_partial_component_matches(chosen, group_ink)
    return chosen if _covered(chosen) == group_ink else []


def analyse_row_exact_grouped_with_baseline_fallback(
    crop,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> dict:
    """Allow exact safe groups to choose a local ±1 baseline independently.

    The ordinary grouped matcher first chooses the best baseline for the whole
    physical row. Any safe-whitespace group that remains incomplete is then
    retried one pixel above and below that main baseline.

    A local fallback is accepted whenever one of those alternate baselines
    explains *all* source ink in the group exactly. A single exact glyph is
    enough evidence; there is no artificial two-glyph requirement. This also
    means the first group on a row gets the same chance as every later group.

    The decision remains purely pixel/facit based. JSONL text is never used.
    """
    model_rows = list(models)
    result = analyse_row_exact_grouped(crop, model_rows, threshold=threshold)
    main_baseline = result.get("baseline")
    groups = list(result.get("safe_groups") or [])
    if main_baseline is None or not groups or result.get("fully_exact"):
        result["baseline_fallbacks"] = []
        result["baseline_segments"] = (
            [{"left": 0, "right": crop.width, "baseline": int(main_baseline)}]
            if main_baseline is not None
            else []
        )
        return result

    candidates, bounds = exact_matches_by_safe_gaps(
        result["ink"], crop.width, crop.height, model_rows
    )
    if bounds != groups:
        groups = bounds

    selected = list(result["selected"])
    fallbacks: list[dict] = []

    for group_index, (left, right) in enumerate(groups):
        group_ink = {(x, y) for x, y in result["ink"] if left <= x < right}
        if not group_ink:
            continue

        existing = [m for m in selected if left <= m.x < right]
        if _covered(existing) == group_ink:
            continue

        best = None
        for delta in (-1, 1):
            baseline = int(main_baseline) + delta
            chosen = _exact_group_at_baseline(
                candidates,
                group_ink,
                left=left,
                right=right,
                baseline=baseline,
            )
            if not chosen:
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
        local_baseline = int(main_baseline) + int(delta)
        selected = [m for m in selected if not (left <= m.x < right)] + list(chosen)
        fallbacks.append(
            {
                "group": group_index,
                "left": left,
                "right": right,
                "from_baseline": int(main_baseline),
                "to_baseline": local_baseline,
                "delta": int(delta),
                "labels": "".join(m.label for m in sorted(chosen, key=lambda m: m.x)),
                "pixels": len(group_ink),
                "status": "full-exact-local-baseline-fallback",
            }
        )

    selected.sort(key=lambda m: (m.x, m.baseline, m.label, m.style))
    covered = _covered(selected)
    unmatched = result["ink"] - covered
    result["selected"] = selected
    result["covered_pixels"] = len(covered)
    result["unmatched_pixels"] = len(unmatched)
    result["fully_exact"] = bool(result["ink"]) and covered == result["ink"]
    result["baseline_fallbacks"] = sorted(
        fallbacks,
        key=lambda item: (int(item["group"]), str(item["status"])),
    )

    # This field is diagnostic only. Keep the main physical-row baseline and
    # list each exact local deviation explicitly rather than pretending one
    # shift persists through unrelated whitespace groups.
    result["baseline_segments"] = [
        {"left": 0, "right": crop.width, "baseline": int(main_baseline)}
    ] + [
        {
            "left": int(item["left"]),
            "right": int(item["right"]),
            "baseline": int(item["to_baseline"]),
        }
        for item in result["baseline_fallbacks"]
    ]
    return result
