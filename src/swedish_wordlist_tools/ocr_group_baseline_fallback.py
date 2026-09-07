from __future__ import annotations

from time import perf_counter
from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_facit_write_redirect import install_facit_write_redirect
from .ocr_glyph_gap_matcher import (
    _drop_partial_component_matches,
    exact_matches_by_safe_gaps,
)
from .ocr_glyph_matcher import (
    GlyphModel,
    Match,
    exact_matches,
    select_best_disjoint_exact_for_ink,
)
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


install_facit_write_redirect()


def _trace_stage(name: str, elapsed: float, **fields) -> None:
    if elapsed < 0.2:
        return
    page = getattr(priority._tls, "trace_page", None)
    position = getattr(priority._tls, "trace_position", None)
    where = ""
    if page is not None and position is not None:
        where = f" page {page} column {position[0]} row {position[1]}"
    extra = "".join(f" {key}={value}" for key, value in fields.items())
    print(f"glyph-stage:{where} stage={name} elapsed={elapsed:.3f}s{extra}", flush=True)


def _covered(matches: Iterable[Match]) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def _anchor_scan_key(match: Match) -> tuple[int, int, int, int, int, str, str]:
    """Order exact anchors like a raster scan: top row first, then leftmost.

    A model is positioned relative to its baseline.  Consequently the first
    exact glyph found this way supplies a baseline without us having to guess
    one from the row geometry.  The remaining fields only make ties stable and
    favour stronger learned glyphs.
    """
    top = min(y for _x, y in match.pixels)
    left = min(x for x, _y in match.pixels)
    return (
        top,
        left,
        -match.model_pixels,
        -match.sources,
        match.baseline,
        match.label,
        match.style,
    )


def _baseline_anchor_candidates(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    line_start_left: int = 0,
    line_start_right: int | None = None,
) -> list[Match]:
    """Find permissive exact glyphs that may anchor a previously missing baseline.

    Whole-component ownership is deliberately disabled here.  Printed adjacent
    glyphs can touch, and this fallback is specifically for rows where the safe
    grouping could not establish any baseline.  Search order mirrors scanning
    pixel rows down from the top and, on each row, from the line-start region's
    left edge toward the right.
    """
    right = width if line_start_right is None else max(line_start_left, min(width, int(line_start_right)))
    left = max(0, min(width, int(line_start_left)))
    candidates = exact_matches(
        ink,
        width,
        height,
        models,
        require_whole_components=False,
    )
    return sorted(
        (
            match
            for match in candidates
            if any(left <= x < right for x, _y in match.pixels)
        ),
        key=_anchor_scan_key,
    )


def _select_at_baseline(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    baseline: int,
) -> list[Match]:
    candidates = exact_matches(
        ink,
        width,
        height,
        models,
        baseline_only=int(baseline),
        require_whole_components=False,
    )
    return select_best_disjoint_exact_for_ink(candidates, ink)


def _anchor_missing_baseline(
    result: dict,
    crop,
    models: Iterable[GlyphModel],
    *,
    line_start_left: int = 0,
    line_start_right: int | None = None,
) -> dict:
    """Use the first useful exact line-start glyph to recover a missing baseline."""
    if result.get("baseline") is not None or not result.get("ink"):
        return result

    model_rows = list(models)
    started = perf_counter()
    anchors = _baseline_anchor_candidates(
        result["ink"],
        crop.width,
        crop.height,
        model_rows,
        line_start_left=line_start_left,
        line_start_right=line_start_right,
    )
    _trace_stage(
        "missing_baseline_anchor_candidates",
        perf_counter() - started,
        candidates=len(anchors),
    )

    tried: set[int] = set()
    for anchor in anchors:
        baseline = int(anchor.baseline)
        if baseline in tried:
            continue
        tried.add(baseline)
        selected = _select_at_baseline(
            result["ink"], crop.width, crop.height, model_rows, baseline
        )
        if not selected:
            continue
        # The anchor itself must survive the baseline-constrained partition.
        # Otherwise some accidental contained shape could dictate the row.
        if not any(match == anchor for match in selected):
            continue

        covered = _covered(selected)
        result["baseline"] = baseline
        result["selected"] = sorted(
            selected, key=lambda m: (m.x, m.baseline, m.label, m.style)
        )
        result["covered_pixels"] = len(covered)
        result["unmatched_pixels"] = len(result["ink"] - covered)
        result["fully_exact"] = bool(result["ink"]) and covered == result["ink"]
        result["baseline_anchor"] = {
            "label": anchor.label,
            "style": anchor.style,
            "x": int(anchor.x),
            "top": min(y for _x, y in anchor.pixels),
            "baseline": baseline,
            "pixels": int(anchor.model_pixels),
            "sources": int(anchor.sources),
            "status": "exact-glyph-line-start-anchor",
        }
        return result

    result["baseline_anchor"] = None
    return result


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
    """Recover missing baselines, then allow local exact groups a ±1 baseline."""
    model_rows = list(models)
    result = analyse_row_exact_grouped(crop, model_rows, threshold=threshold)
    if result.get("baseline") is None:
        result = _anchor_missing_baseline(result, crop, model_rows)

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

    cached_candidates = result.pop("_exact_candidates", None)
    if cached_candidates is not None:
        candidates = list(cached_candidates)
        bounds = groups
        result["baseline_candidate_source"] = "reused-exhaustive-safe-groups"
    else:
        started = perf_counter()
        candidates, bounds = exact_matches_by_safe_gaps(
            result["ink"], crop.width, crop.height, model_rows
        )
        _trace_stage(
            "local_baseline_candidates",
            perf_counter() - started,
            groups=len(bounds),
            candidates=len(candidates),
            baseline=main_baseline,
        )
        result["baseline_candidate_source"] = "regenerated"

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
            started = perf_counter()
            chosen = _exact_group_at_baseline(
                candidates,
                group_ink,
                left=left,
                right=right,
                baseline=baseline,
            )
            _trace_stage(
                "local_baseline_select",
                perf_counter() - started,
                group=group_index,
                delta=delta,
                group_pixels=len(group_ink),
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
