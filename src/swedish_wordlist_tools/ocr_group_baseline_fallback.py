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
    """Keep one row baseline, with a conservative whitespace-triggered ±1 fallback.

    The ordinary grouped matcher remains authoritative. Only after it has chosen
    one baseline for the complete physical row do we inspect later safe-whitespace
    groups which remain incomplete. A group may move by one pixel only if the
    alternate baseline explains the *entire* group's source ink exactly with at
    least two glyphs.

    Once such a later group has proved a local baseline shift, the immediately
    preceding incomplete group may be retried at that already-proved baseline.
    This lets a single first glyph of a shifted phrase follow the proven shift,
    without allowing one isolated glyph to establish a new baseline by itself.
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
            chosen = _exact_group_at_baseline(
                candidates,
                group_ink,
                left=left,
                right=right,
                baseline=baseline,
            )
            if len(chosen) < 2:
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
        proven_baseline = int(main_baseline) + int(delta)
        selected = [m for m in selected if not (left <= m.x < right)] + list(chosen)
        fallbacks.append(
            {
                "group": group_index,
                "left": left,
                "right": right,
                "from_baseline": int(main_baseline),
                "to_baseline": proven_baseline,
                "delta": int(delta),
                "labels": "".join(m.label for m in sorted(chosen, key=lambda m: m.x)),
                "pixels": len(group_ink),
                "status": "full-exact-whitespace-fallback",
            }
        )

        # A single glyph immediately before the proving group was deliberately
        # not allowed to establish a shift. Now that the following group has
        # proved it, retry exactly that one preceding incomplete group at the
        # same baseline. Never walk farther backwards.
        previous_index = group_index - 1
        if previous_index <= 0:
            continue
        previous_left, previous_right = groups[previous_index]
        previous_ink = {
            (x, y)
            for x, y in result["ink"]
            if previous_left <= x < previous_right
        }
        previous_existing = [
            m for m in selected if previous_left <= m.x < previous_right
        ]
        if not previous_ink or _covered(previous_existing) == previous_ink:
            continue
        previous_chosen = _exact_group_at_baseline(
            candidates,
            previous_ink,
            left=previous_left,
            right=previous_right,
            baseline=proven_baseline,
        )
        if not previous_chosen:
            continue
        selected = [
            m for m in selected if not (previous_left <= m.x < previous_right)
        ] + list(previous_chosen)
        fallbacks.append(
            {
                "group": previous_index,
                "left": previous_left,
                "right": previous_right,
                "from_baseline": int(main_baseline),
                "to_baseline": proven_baseline,
                "delta": int(delta),
                "labels": "".join(
                    m.label for m in sorted(previous_chosen, key=lambda m: m.x)
                ),
                "pixels": len(previous_ink),
                "status": "retroactive-preceding-group-fallback",
                "proved_by_group": group_index,
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
    return result
