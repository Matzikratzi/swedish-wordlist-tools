from __future__ import annotations

"""Bounded exact-cover fallback allowing one local baseline shift of +/-1.

This is a regression-scan fast path, not an exhaustive matcher. It reuses the
page-prepared candidate buckets and the same left-edge anchoring as the normal
fast cover, but allows the baseline to switch once by one raster line. The
switch then remains in force for the rest of the row.
"""

from dataclasses import dataclass
from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_page_cached_fast_path import _bound_page_candidates, _iter_candidates


@dataclass(frozen=True)
class TwoBaselineExactResult:
    baseline: int
    selected: tuple[Match, ...]
    placements_tested: int
    baseline_switches: tuple[dict, ...]


def fast_exact_cover_one_baseline_switch(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    max_states: int = 20000,
) -> TwoBaselineExactResult | None:
    """Exact-cover with at most one persistent +/-1 baseline switch."""
    if not ink:
        return None

    page_candidates = _bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, int | None, bool, bool]] = set()
    states = 0
    placements_tested = 0

    def search(
        remaining: frozenset[tuple[int, int]],
        initial_baseline: int | None,
        active_baseline: int | None,
        switched: bool,
        previous_style: str | None,
        leading_homonym_seen: bool,
    ) -> tuple[tuple[Match, ...], tuple[dict, ...]] | None:
        nonlocal states, placements_tested
        if not remaining:
            return (), ()

        state = (remaining, initial_baseline, active_baseline, switched, leading_homonym_seen)
        if state in failed:
            return None
        states += 1
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)

        for model, min_x, left_pixels in _iter_candidates(
            page_candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=active_baseline is not None,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            for _mx, my in left_pixels:
                candidate_baseline = anchor_y - my
                if candidate_baseline < -model.min_y:
                    continue
                if candidate_baseline > height - 1 - model.max_y:
                    continue

                is_leading_homonym = (
                    first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
                )

                next_initial = initial_baseline
                next_active = active_baseline
                next_switched = switched
                switch_record: tuple[dict, ...] = ()

                if is_leading_homonym:
                    # Homonym digit owns its own vertical placement and does not
                    # establish the normal headword baseline.
                    pass
                elif active_baseline is None:
                    next_initial = candidate_baseline if initial_baseline is None else initial_baseline
                    next_active = candidate_baseline
                elif candidate_baseline == active_baseline:
                    pass
                elif (
                    not switched
                    and initial_baseline is not None
                    and candidate_baseline in {active_baseline - 1, active_baseline + 1}
                ):
                    next_active = candidate_baseline
                    next_switched = True
                    switch_record = ({
                        "x": x0,
                        "from_baseline": active_baseline,
                        "to_baseline": candidate_baseline,
                        "delta": candidate_baseline - active_baseline,
                    },)
                else:
                    continue

                placements_tested += 1
                placed = frozenset(
                    (x0 + x, candidate_baseline + y) for x, y in model.pixels
                )
                if not placed.issubset(remaining):
                    continue

                match = Match(
                    label=model.label,
                    style=model.style,
                    x=x0,
                    baseline=candidate_baseline,
                    pixels=placed,
                    model_pixels=len(model.pixels),
                    sources=model.sources,
                )
                saw_homonym = leading_homonym_seen or is_leading_homonym
                tail = search(
                    frozenset(remaining.difference(placed)),
                    next_initial,
                    next_active,
                    next_switched,
                    priority._typographic_style(model.style),
                    saw_homonym,
                )
                if tail is not None:
                    tail_matches, tail_switches = tail
                    return (match,) + tail_matches, switch_record + tail_switches

        failed.add(state)
        return None

    chosen = search(target, None, None, False, None, False)
    if chosen is None:
        return None

    matches, switches = chosen
    selected = tuple(sorted(matches, key=lambda m: (m.x, m.baseline, m.label, str(m.style))))
    if row_kind == "homonym" and selected and priority._is_homonym_match(selected[0]):
        normal = next((m for m in selected[1:] if not priority._is_homonym_match(m)), None)
        baseline = normal.baseline if normal is not None else selected[0].baseline
    else:
        baseline = selected[0].baseline
    return TwoBaselineExactResult(
        baseline=baseline,
        selected=selected,
        placements_tested=placements_tested,
        baseline_switches=tuple(switches),
    )
