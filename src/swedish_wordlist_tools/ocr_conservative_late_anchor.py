from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_group_baseline_fallback import (
    _covered,
    _iter_baseline_anchor_candidates,
    _select_at_baseline,
)


@dataclass(frozen=True)
class LateAnchorRepair:
    old_baseline: int
    old_left: int
    ink_left: int
    new_baseline: int
    new_label: str
    new_style: str
    new_left: int
    covered_pixels: int
    source_pixels: int


def _selected_left(selected: Iterable[Match]) -> int | None:
    points = [x for match in selected for x, _y in match.pixels]
    return min(points) if points else None


def _anchor_left(anchor: Match) -> int:
    return min(x for x, _y in anchor.pixels)


def repair_late_baseline_anchor(
    result: dict,
    crop,
    models: Iterable[GlyphModel],
    *,
    trigger_gap: int = 12,
    allowed_start_gap: int = 6,
) -> tuple[dict, LateAnchorRepair | None]:
    """Repair the #2 failure: a high glyph far into the row anchors baseline.

    This is deliberately a second-pass guard.  Ordinary rows are untouched.
    We only intervene when the parser has already chosen a baseline whose
    selected ink starts substantially to the right of the row's actual ink.
    Re-anchoring then keeps the old raster-order search, but only accepts an
    exact glyph close to the left edge of the row ink.  Thus low start glyphs
    may establish the baseline even when a later diacritic/ascender appears
    higher in the raster.
    """
    ink = set(result.get("ink") or ())
    selected = list(result.get("selected") or ())
    baseline = result.get("baseline")
    if baseline is None or not ink or not selected:
        return result, None

    ink_left = min(x for x, _y in ink)
    selected_left = _selected_left(selected)
    if selected_left is None or selected_left - ink_left < int(trigger_gap):
        return result, None

    model_rows = list(models)
    tried: set[int] = set()
    for anchor in _iter_baseline_anchor_candidates(
        ink,
        crop.width,
        crop.height,
        model_rows,
    ):
        anchor_left = _anchor_left(anchor)
        if anchor_left > ink_left + int(allowed_start_gap):
            continue
        candidate_baseline = int(anchor.baseline)
        if candidate_baseline in tried:
            continue
        tried.add(candidate_baseline)
        candidate_selected = _select_at_baseline(
            ink,
            crop.width,
            crop.height,
            model_rows,
            candidate_baseline,
        )
        if not candidate_selected:
            continue
        if not any(match == anchor for match in candidate_selected):
            continue

        covered = _covered(candidate_selected)
        repaired = dict(result)
        repaired["baseline"] = candidate_baseline
        repaired["selected"] = sorted(
            candidate_selected,
            key=lambda m: (m.x, m.baseline, m.label, m.style),
        )
        repaired["covered_pixels"] = len(covered)
        repaired["unmatched_pixels"] = len(ink - covered)
        repaired["fully_exact"] = bool(ink) and covered == ink
        repaired["baseline_anchor"] = {
            "label": anchor.label,
            "style": anchor.style,
            "x": int(anchor.x),
            "top": min(y for _x, y in anchor.pixels),
            "baseline": candidate_baseline,
            "pixels": int(anchor.model_pixels),
            "sources": int(anchor.sources),
            "status": "conservative-left-edge-reanchor",
        }
        record = LateAnchorRepair(
            old_baseline=int(baseline),
            old_left=int(selected_left),
            ink_left=int(ink_left),
            new_baseline=candidate_baseline,
            new_label=anchor.label,
            new_style=anchor.style,
            new_left=int(anchor_left),
            covered_pixels=len(covered),
            source_pixels=len(ink),
        )
        repaired["conservative_late_anchor_repair"] = record
        return repaired, record

    return result, None


def guarded_analyser(
    original_analyse: Callable,
    *,
    on_repair: Callable[[LateAnchorRepair], None] | None = None,
):
    """Wrap an existing row analyser with the conservative #2 repair."""

    def analyse(crop, models, *, threshold: int = 210):
        result = original_analyse(crop, models, threshold=threshold)
        result, record = repair_late_baseline_anchor(result, crop, models)
        if record is not None and on_repair is not None:
            on_repair(record)
        return result

    return analyse
