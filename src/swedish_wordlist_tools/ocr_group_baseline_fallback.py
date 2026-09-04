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
    """Keep a piecewise-constant row baseline with conservative ±1 discovery.

    The ordinary grouped matcher first chooses one baseline for the complete
    physical row. A later safe-whitespace group may establish a one-pixel shift
    only if the alternate baseline explains the *entire* group's source ink
    exactly with at least two glyphs.

    Once such a shift is proved, that baseline is treated as the support line
    for the rest of the physical row. Subsequent incomplete whitespace groups
    are therefore retried at the already-proved baseline even when they contain
    only one glyph. This is still purely pixel/facit based; no JSONL text is
    consulted. Earlier unresolved groups may also inherit the proved baseline,
    but only while each group is explained completely and exactly at that same
    baseline.
    """
    model_rows = list(models)
    result = analyse_row_exact_grouped(crop, model_rows, threshold=threshold)
    main_baseline = result.get("baseline")
    groups = list(result.get("safe_groups") or [])
    if main_baseline is None or len(groups) < 2 or result.get("fully_exact"):
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
    active_baseline = int(main_baseline)
    shift_start_left: int | None = None

    for group_index, (left, right) in enumerate(groups):
        if group_index == 0:
            continue
        group_ink = {(x, y) for x, y in result["ink"] if left <= x < right}
        if not group_ink:
            continue
        existing = [m for m in selected if left <= m.x < right]
        if _covered(existing) == group_ink:
            continue

        # A previously proved support-line shift persists to the end of the row.
        # It no longer needs two glyphs in every later group: the earlier proof
        # established the baseline, while this group still has to match *all* of
        # its pixels exactly at that same baseline.
        if active_baseline != int(main_baseline):
            inherited = _exact_group_at_baseline(
                candidates,
                group_ink,
                left=left,
                right=right,
                baseline=active_baseline,
            )
            if inherited:
                selected = [m for m in selected if not (left <= m.x < right)] + list(inherited)
                fallbacks.append(
                    {
                        "group": group_index,
                        "left": left,
                        "right": right,
                        "from_baseline": int(main_baseline),
                        "to_baseline": active_baseline,
                        "delta": active_baseline - int(main_baseline),
                        "labels": "".join(
                            m.label for m in sorted(inherited, key=lambda m: m.x)
                        ),
                        "pixels": len(group_ink),
                        "status": "persistent-proven-baseline-fallback",
                    }
                )
            # Once a support line has been proved we do not hunt for another
            # independent ±1 shift later on the same physical row.
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
        active_baseline = proven_baseline
        shift_start_left = left
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

        # The proving group establishes a real support-line shift. Walk left
        # across preceding unresolved safe groups while each one is explained
        # completely at the same proved baseline. Stop at the first group that
        # is already complete on the main baseline or cannot be covered exactly.
        for previous_index in range(group_index - 1, -1, -1):
            previous_left, previous_right = groups[previous_index]
            previous_ink = {
                (x, y)
                for x, y in result["ink"]
                if previous_left <= x < previous_right
            }
            previous_existing = [
                m for m in selected if previous_left <= m.x < previous_right
            ]
            if not previous_ink:
                continue
            if _covered(previous_existing) == previous_ink:
                break
            previous_chosen = _exact_group_at_baseline(
                candidates,
                previous_ink,
                left=previous_left,
                right=previous_right,
                baseline=proven_baseline,
            )
            if not previous_chosen:
                break
            shift_start_left = previous_left
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
                    "status": "retroactive-proven-baseline-fallback",
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
    if shift_start_left is None:
        result["baseline_segments"] = [
            {"left": 0, "right": crop.width, "baseline": int(main_baseline)}
        ]
    else:
        result["baseline_segments"] = [
            {"left": 0, "right": int(shift_start_left), "baseline": int(main_baseline)},
            {"left": int(shift_start_left), "right": crop.width, "baseline": int(active_baseline)},
        ]
    return result
