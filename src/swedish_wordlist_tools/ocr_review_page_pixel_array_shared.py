from __future__ import annotations

"""Shared page-pixel review path used by both scanners and review editors.

All automatic row-ownership repair belongs here so batch classification and
interactive review see the same state.
"""

from time import perf_counter

from . import ocr_probe_row_glyphs_grouped as grouped_probe
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs
from .ocr_page_cached_fast_path import (
    bind_page_candidates,
    page_cached_prioritized_fast_exact_cover,
)
from .ocr_priority_fast_path import (
    classify_row_start,
    observe_row_layout,
    set_row_priority_hint,
)
from .ocr_probe_merge_with_lower_row import apply_merge_down, probe_zero_match_merge_down


# Restore the ordinary page-cached fast path.  The x-segmented and baseline-seed
# experiments remain in the tree for later inspection but are deliberately not
# active: page 9-10 benchmarks showed substantial regressions for both.
grouped_probe.fast_exact_cover = page_cached_prioritized_fast_exact_cover

_base_load_review_state_pixel_array = page_editor.load_review_state_pixel_array


def _mark_absorbed_empty(state: dict, proof: dict) -> dict:
    """An emptied segmentation artefact is complete, not a review defect."""
    out = dict(state)
    if int(out.get("source_pixels") or 0) == 0:
        out["fully_exact"] = True
        out["row_absorbed_by_lower"] = proof
    return out


def _base_load_with_priority(context, position, models):
    """Run the unchanged row analyser with a result-neutral candidate hint."""
    bind_page_candidates(context, models)
    set_row_priority_hint(classify_row_start(context, position))
    state = _base_load_review_state_pixel_array(context, position, models)
    observe_row_layout(context, state)
    return state


def _probe_merge_down_if_zero_match(context, position, state, models, timings):
    """Probe the following row only for the narrow zero-match artefact case."""
    if int(state.get("source_pixels") or 0) <= 0 or state.get("matches"):
        return None

    column, row_index = map(int, position)
    columns = context.get("row_map", {}).get("columns") or []
    rows = columns[column].get("rows") or [] if 0 <= column < len(columns) else []
    if row_index + 1 >= len(rows):
        return None

    lower_position = (column, row_index + 1)
    started = perf_counter()
    lower_state = _base_load_with_priority(context, lower_position, models)
    timings["merge_lower_base"] = perf_counter() - started
    started = perf_counter()
    proof = probe_zero_match_merge_down(context, state, lower_state, models)
    timings["merge_probe"] = perf_counter() - started
    return proof


def _attach_timings(state: dict, timings: dict[str, float]) -> dict:
    state["shared_stage_timings"] = dict(timings)
    return state


def load_review_state_pixel_array(context, position, models):
    timings: dict[str, float] = {}

    started = perf_counter()
    state = _base_load_with_priority(context, position, models)
    timings["initial_base"] = perf_counter() - started
    if state.get("fully_exact"):
        return _attach_timings(state, timings)

    if int(state.get("source_pixels") or 0) > 0 and not state.get("matches"):
        context["analyse_row_exact"] = page_editor.fast.analyse_row_exact
        proof = _probe_merge_down_if_zero_match(context, position, state, models, timings)
        if proof is not None:
            started = perf_counter()
            moved = apply_merge_down(context, proof)
            timings["merge_apply"] = perf_counter() - started
            if moved:
                column, row_index = map(int, position)
                if not context.get("quiet_successful_ownership"):
                    print(
                        f"review: provmerge c{column} r{row_index}/{row_index + 1}: "
                        f"täckning {proof['lower_covered_pixels']}→{proof['covered_pixels']} px; "
                        f"flyttade {moved} px nedåt, text={proof['labels']!r}",
                        flush=True,
                    )
                started = perf_counter()
                state = _base_load_with_priority(context, position, models)
                timings["merge_reanalyse"] = perf_counter() - started
                state = _mark_absorbed_empty(state, proof)
                return _attach_timings(state, timings)

    started = perf_counter()
    records = repair_lower_row_disconnected_glyphs(context, state, models)
    timings["disconnected_repair"] = perf_counter() - started
    if records:
        started = perf_counter()
        state = _base_load_with_priority(context, position, models)
        timings["disconnected_reanalyse"] = perf_counter() - started
        state["disconnected_glyph_ownership"] = records

    return _attach_timings(state, timings)


build_page_context_pixel_array = page_editor.build_page_context_pixel_array
