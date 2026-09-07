from __future__ import annotations

from typing import Iterable, Iterator

from .ocr_glyph_facit_write_redirect import install_facit_write_redirect
from .ocr_glyph_matcher import (
    GlyphModel,
    Match,
    _ink_components,
    exact_matches,
)
from .ocr_page_cached_fast_path import analyse_row_prioritized


install_facit_write_redirect()

# Compatibility hook used by the benchmark layers.  It deliberately starts as
# the same shared parser used by the editor/batch path; benchmark experiments may
# temporarily replace this name and the wrapper below will see that replacement.
analyse_row_exact_grouped = analyse_row_prioritized


def _covered(matches: Iterable[Match]) -> set[tuple[int, int]]:
    rows = list(matches)
    return set().union(*(match.pixels for match in rows)) if rows else set()


def _anchor_scan_key(match: Match) -> tuple[int, int, int, int, int, str, str]:
    """Order exact candidates as a top-to-bottom, left-to-right raster scan."""
    return (
        min(y for _x, y in match.pixels),
        min(x for x, _y in match.pixels),
        -match.model_pixels,
        -match.sources,
        match.baseline,
        match.label,
        match.style,
    )


def _iter_baseline_anchor_candidates(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    line_start_left: int = 0,
    line_start_right: int | None = None,
) -> Iterator[Match]:
    """Yield exact baseline anchors lazily in the old raster-sort order.

    The previous implementation called ``exact_matches`` for every model, x
    placement and baseline on the complete row, materialised every hit, then
    sorted all of them merely to inspect the first useful baseline.  Here we
    invert the loops to the actual ordering criterion: top raster y first,
    then placed left x.  At one raster position we keep the same remaining
    tie-break as ``_anchor_scan_key``.  Therefore fallback decisions are
    unchanged, while ordinary cases stop as soon as their first accepted
    baseline has been tested.
    """
    if not ink:
        return

    left = max(0, min(width, int(line_start_left)))
    right = width if line_start_right is None else max(left, min(width, int(line_start_right)))
    model_rows = list(models)

    prepared: list[tuple[GlyphModel, int, int, tuple[tuple[int, int], ...]]] = []
    for model in model_rows:
        if not model.pixels:
            continue
        min_x = min(x for x, _y in model.pixels)
        top_y = model.min_y
        top_pixels = tuple(sorted((x, y) for x, y in model.pixels if y == top_y))
        prepared.append((model, min_x, top_y, top_pixels))

    # A match can only have its top raster row on an ink-bearing y.  Likewise,
    # its leftmost occupied x must be an ink-bearing x on some model pixel, so
    # scanning only the bounding raster positions that can overlap ink avoids
    # the old width*height*models baseline sweep.
    ink_by_y: dict[int, set[int]] = {}
    for x, y in ink:
        ink_by_y.setdefault(y, set()).add(x)

    for top in sorted(ink_by_y):
        candidates_at_top: list[Match] = []
        for model, min_x, model_top, top_pixels in prepared:
            baseline = top - model_top
            if baseline < -model.min_y or baseline > height - 1 - model.max_y:
                continue

            # Every valid placement has at least one model-top pixel on this
            # raster row.  Use those source x positions to derive possible x0
            # values instead of sweeping the complete row width.
            x0_values: set[int] = set()
            source_xs = ink_by_y[top]
            for model_x, _model_y in top_pixels:
                for source_x in source_xs:
                    x0_values.add(source_x - model_x)

            for x0 in sorted(x0_values):
                placed_left = x0 + min_x
                if placed_left < left or placed_left >= right:
                    continue
                if x0 < 0 or x0 + model.width > width:
                    continue
                fits = True
                for x, y in model.pixels:
                    if (x0 + x, baseline + y) not in ink:
                        fits = False
                        break
                if not fits:
                    continue
                placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
                candidates_at_top.append(
                    Match(
                        label=model.label,
                        style=model.style,
                        x=x0,
                        baseline=baseline,
                        pixels=placed,
                        model_pixels=len(model.pixels),
                        sources=model.sources,
                    )
                )

        # The old global sort compares left x before model/source tie-breaks.
        # Sorting only this top-y bucket is therefore exactly equivalent, and
        # allows the caller to stop before any lower raster row is inspected.
        candidates_at_top.sort(key=_anchor_scan_key)
        yield from candidates_at_top


def _baseline_anchor_candidates(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    line_start_left: int = 0,
    line_start_right: int | None = None,
) -> list[Match]:
    """Compatibility wrapper returning all raster-ordered anchor candidates."""
    return list(
        _iter_baseline_anchor_candidates(
            ink,
            width,
            height,
            models,
            line_start_left=line_start_left,
            line_start_right=line_start_right,
        )
    )


def _select_best_disjoint_exact_for_ink_fast(
    matches: Iterable[Match],
    ink: set[tuple[int, int]],
    *,
    beam_width: int = 512,
) -> list[Match]:
    """Exact equivalent of the old beam selector using integer pixel masks.

    The fallback used to spend seconds repeatedly unioning frozensets and
    rescanning all source components for every beam state.  Keep exactly the
    same candidate order, score tuple, occupied-state deduplication and beam
    width, but represent occupied pixels as one Python integer and update the
    component-completeness score only for components touched by the new match.
    """
    rows = sorted(
        matches,
        key=lambda m: (-m.model_pixels, -m.score, -m.sources, m.x, m.label, m.style),
    )
    if not rows:
        return []

    point_bits = {point: 1 << index for index, point in enumerate(sorted(ink))}
    components, by_pixel = _ink_components(ink)
    component_masks: list[tuple[int, int]] = []
    for component in components:
        mask = 0
        for point in component:
            mask |= point_bits[point]
        component_masks.append((mask, len(component)))

    prepared: list[tuple[Match, int, tuple[int, ...]]] = []
    for match in rows:
        mask = 0
        touched: set[int] = set()
        for point in match.pixels:
            bit = point_bits.get(point)
            if bit is None:
                # exact_matches() never emits this, but keep this helper safe
                # when unit tests construct Match objects directly.
                mask = 0
                touched.clear()
                break
            mask |= bit
            touched.add(by_pixel[point])
        if mask:
            prepared.append((match, mask, tuple(sorted(touched))))

    # State key is exactly _component_partition_key():
    # (complete_component_pixels, model_pixels, model_pixels^2, sources, -count)
    states: list[tuple[tuple[Match, ...], int, tuple[int, int, int, int, int]]] = [
        ((), 0, (0, 0, 0, 0, 0))
    ]

    for match, match_mask, touched_components in prepared:
        expanded = list(states)
        for chosen, occupied, key in states:
            if occupied & match_mask:
                continue
            new_occupied = occupied | match_mask
            complete_pixels = key[0]
            for component_index in touched_components:
                component_mask, component_pixels = component_masks[component_index]
                if (
                    occupied & component_mask != component_mask
                    and new_occupied & component_mask == component_mask
                ):
                    complete_pixels += component_pixels
            new_key = (
                complete_pixels,
                key[1] + match.model_pixels,
                key[2] + match.model_pixels * match.model_pixels,
                key[3] + match.sources,
                key[4] - 1,
            )
            expanded.append((chosen + (match,), new_occupied, new_key))

        best_by_occupied: dict[
            int, tuple[tuple[Match, ...], tuple[int, int, int, int, int]]
        ] = {}
        for chosen, occupied, key in expanded:
            previous = best_by_occupied.get(occupied)
            if previous is None or key > previous[1]:
                best_by_occupied[occupied] = (chosen, key)

        states = sorted(
            (
                (chosen, occupied, key)
                for occupied, (chosen, key) in best_by_occupied.items()
            ),
            key=lambda state: state[2],
            reverse=True,
        )[:beam_width]

    best = max(states, key=lambda state: state[2])[0] if states else ()
    return sorted(best, key=lambda m: (m.x, m.baseline, m.label, m.style))


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
    return _select_best_disjoint_exact_for_ink_fast(candidates, ink)


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
    anchors = _iter_baseline_anchor_candidates(
        result["ink"],
        crop.width,
        crop.height,
        model_rows,
        line_start_left=line_start_left,
        line_start_right=line_start_right,
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
        # The glyph that proposed the baseline must survive the constrained
        # partition; otherwise an accidental contained shape must not steer us.
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


def analyse_row_exact_grouped_with_baseline_fallback(
    crop,
    models: Iterable[GlyphModel],
    *,
    threshold: int = 210,
) -> dict:
    """Shared parser plus exact-glyph anchoring when no baseline was found."""
    model_rows = list(models)
    result = analyse_row_exact_grouped(crop, model_rows, threshold=threshold)
    if result.get("baseline") is None:
        result = _anchor_missing_baseline(result, crop, model_rows)

    baseline = result.get("baseline")
    result["baseline_fallbacks"] = []
    result["baseline_segments"] = (
        [{"left": 0, "right": crop.width, "baseline": int(baseline)}]
        if baseline is not None
        else []
    )
    return result
