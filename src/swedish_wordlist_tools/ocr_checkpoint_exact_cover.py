from __future__ import annotations

"""Conservative left-to-right exact-cover checkpoints.

This path is attempted only after the ordinary bounded fast path has failed and
before the exhaustive safe-group fallback.  It may commit an exact left prefix
once enough horizontal progress has been made, while retaining a configurable
backtrack window.  A checkpoint result is returned only if the *entire* row is
still covered exactly; otherwise callers fall back to the unchanged exhaustive
matcher.
"""

from typing import Iterable

from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import GlyphModel, Match
from .ocr_glyph_popularity_stats import record_model_hit
from .ocr_page_cached_fast_path import _bound_page_candidates, _iter_candidates


DEFAULT_CHECKPOINT_SPAN = 20
DEFAULT_BACKTRACK_SPAN = 10
DEFAULT_MAX_STATES_PER_PHASE = 2000


def checkpoint_page_cached_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models: Iterable[GlyphModel],
    *,
    checkpoint_span: int = DEFAULT_CHECKPOINT_SPAN,
    backtrack_span: int = DEFAULT_BACKTRACK_SPAN,
    max_states_per_phase: int = DEFAULT_MAX_STATES_PER_PHASE,
) -> tuple[int, list[Match], int] | None:
    """Try a complete exact cover while limiting leftward reconsideration.

    After at least ``checkpoint_span`` x-pixels of exact progress, glyphs ending
    strictly left of ``front_x - backtrack_span`` are frozen.  The theoretical
    x boundary is therefore never allowed to cut a glyph: any glyph crossing it
    remains in the live search window and can be reconsidered.

    This is a success-only optimization.  Failure is deliberately inconclusive.
    """
    if not ink or checkpoint_span <= 0 or backtrack_span < 0:
        return None

    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    # Leading raised homonym digits use a separate baseline.  Keep that special
    # case on the proven ordinary/exhaustive paths until checkpoints explicitly
    # model two baseline domains.
    if row_kind == "homonym":
        return None

    page_candidates = _bound_page_candidates(models)
    target = frozenset(ink)
    remaining_global = target
    committed: list[tuple[GlyphModel, Match]] = []
    fixed_baseline: int | None = None
    previous_style: str | None = None
    placements_total = 0
    checkpoint_count = 0
    stats = priority._stats()
    stats["checkpoint_calls"] = stats.get("checkpoint_calls", 0) + 1

    while remaining_global:
        phase_target = remaining_global
        phase_start_x = min(x for x, _y in phase_target)
        failed: set[tuple[frozenset[tuple[int, int]], int | None, bool]] = set()
        states = 0
        phase_placements = 0

        def search(
            remaining: frozenset[tuple[int, int]],
            baseline: int | None,
            prior_style: str | None,
            path: tuple[tuple[GlyphModel, Match], ...],
        ):
            nonlocal states, phase_placements
            if not remaining:
                return ("complete", path)

            front_x = min(x for x, _y in remaining)
            if path and front_x - phase_start_x >= checkpoint_span:
                freeze_before = front_x - backtrack_span
                freeze_count = 0
                for _model, match in path:
                    if match.x1 < freeze_before:
                        freeze_count += 1
                    else:
                        break
                if freeze_count:
                    return ("checkpoint", path[:freeze_count])

            state = (remaining, baseline, False)
            if state in failed:
                return None
            states += 1
            if states > max_states_per_phase:
                return None

            anchor_x = min(x for x, _y in remaining)
            anchor_y = min(y for x, y in remaining if x == anchor_x)
            first_glyph = len(remaining) == len(phase_target)

            for model, min_x, left_pixels in _iter_candidates(
                page_candidates,
                first_glyph=first_glyph,
                previous_style=prior_style,
                row_kind=row_kind,
                leading_homonym_seen=False,
                baseline_established=baseline is not None,
            ):
                x0 = anchor_x - min_x
                if x0 < 0 or x0 + model.width > width:
                    continue
                for _mx, my in left_pixels:
                    candidate_baseline = anchor_y - my
                    if baseline is not None and candidate_baseline != baseline:
                        continue
                    if candidate_baseline < -model.min_y:
                        continue
                    if candidate_baseline > height - 1 - model.max_y:
                        continue
                    phase_placements += 1
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
                    result = search(
                        frozenset(remaining.difference(placed)),
                        candidate_baseline if baseline is None else baseline,
                        priority._typographic_style(model.style),
                        path + ((model, match),),
                    )
                    if result is not None:
                        return result

            failed.add(state)
            return None

        result = search(phase_target, fixed_baseline, previous_style, ())
        placements_total += phase_placements
        if result is None:
            stats["checkpoint_placements"] = stats.get("checkpoint_placements", 0) + placements_total
            stats["checkpoint_commits"] = stats.get("checkpoint_commits", 0) + checkpoint_count
            return None

        kind, rows = result
        if kind == "complete":
            committed.extend(rows)
            remaining_global = frozenset()
            break

        # Freeze only whole glyphs.  Any selected glyph touching the backtrack
        # window was intentionally omitted from ``rows`` and will be searched
        # again in the next phase.
        if not rows:
            stats["checkpoint_placements"] = stats.get("checkpoint_placements", 0) + placements_total
            stats["checkpoint_commits"] = stats.get("checkpoint_commits", 0) + checkpoint_count
            return None
        frozen_pixels = frozenset().union(*(match.pixels for _model, match in rows))
        if not frozen_pixels or not frozen_pixels.issubset(remaining_global):
            return None
        committed.extend(rows)
        remaining_global = frozenset(remaining_global.difference(frozen_pixels))
        fixed_baseline = rows[-1][1].baseline if fixed_baseline is None else fixed_baseline
        previous_style = priority._typographic_style(rows[-1][0].style)
        checkpoint_count += 1

    selected = sorted(
        (match for _model, match in committed),
        key=lambda match: (match.x, match.baseline, match.label, str(match.style)),
    )
    covered = frozenset().union(*(match.pixels for match in selected)) if selected else frozenset()
    if covered != target or not selected:
        return None

    stats["checkpoint_success"] = stats.get("checkpoint_success", 0) + 1
    stats["checkpoint_placements"] = stats.get("checkpoint_placements", 0) + placements_total
    stats["checkpoint_commits"] = stats.get("checkpoint_commits", 0) + checkpoint_count
    for model, _match in committed:
        record_model_hit(model)
    return selected[0].baseline, selected, placements_total
