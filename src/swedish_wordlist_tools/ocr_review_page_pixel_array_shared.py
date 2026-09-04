from __future__ import annotations

"""Shared page-pixel review path used by both scanners and review editors.

All automatic row-ownership repair belongs here so batch classification and
interactive review see the same state.
"""

from time import perf_counter

from . import ocr_probe_row_glyphs_grouped as grouped_probe
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs
from .ocr_page_cached_fast_path import bind_page_candidates
from .ocr_priority_fast_path import (
    classify_row_start,
    observe_row_layout,
    set_row_priority_hint,
)
from .ocr_probe_merge_with_lower_row import apply_merge_down, probe_zero_match_merge_down
from .ocr_traced_page_cached_fast_path import (
    set_trace_row,
    traced_page_cached_prioritized_fast_exact_cover,
)


# Keep the ordinary page-cached search semantics, but instrument slow recursive
# calls. The tracing wrapper is search-order/result neutral.
grouped_probe.fast_exact_cover = traced_page_cached_prioritized_fast_exact_cover

_base_load_review_state_pixel_array = page_editor.load_review_state_pixel_array
_original_load_owned_row_state = page_editor._load_owned_row_state
_original_ensure_known_glyph_ownership = page_editor._ensure_known_glyph_ownership
_original_assign_split_components_below_known_extent = page_editor._assign_split_components_below_known_extent


def _state_page_ink(state: dict) -> set[tuple[int, int]]:
    """Translate one row state's local source ink back to page coordinates."""
    box = state.get("crop_box") or (0, 0, 0, 0)
    left, top = int(box[0]), int(box[1])
    return {
        (left + int(x), top + int(y))
        for x, y in state.get("source_ink_points") or []
    }


def _format_x_damage(changed: set[tuple[int, int]]) -> str:
    if not changed:
        return "none"
    xs = [x for x, _y in changed]
    return f"{min(xs)}..{max(xs)}"


def _traced_load_owned_row_state(context: dict, position: tuple[int, int], models) -> dict:
    """Observe repeated analyses inside the core editor without changing them."""
    state = _original_load_owned_row_state(context, position, models)
    trace = context.get("_row_reanalysis_trace")
    if not trace or tuple(trace.get("position") or ()) != tuple(position):
        return state

    previous = trace.get("state")
    attempt = int(trace.get("attempt") or 0) + 1
    trace["attempt"] = attempt
    if previous is not None:
        changed = _state_page_ink(previous) ^ _state_page_ink(state)
        old_rev = int(previous.get("pixel_owner_revision") or 0)
        new_rev = int(state.get("pixel_owner_revision") or 0)
        old_row_rev = int(previous.get("pixel_owner_row_revision") or 0)
        new_row_rev = int(state.get("pixel_owner_row_revision") or 0)
        old_box = previous.get("crop_box") or (0, 0, 0, 0)
        new_box = state.get("crop_box") or (0, 0, 0, 0)
        reason = str(trace.get("next_reason") or "unknown")
        print(
            "row-reanalyse: "
            f"page {context.get('page_number')} column {position[0]} row {position[1]} "
            f"attempt={attempt} reason={reason} "
            f"revision={old_rev}->{new_rev} row_revision={old_row_rev}->{new_row_rev} "
            f"changed_px={len(changed)} changed_x={_format_x_damage(changed)} "
            f"crop_y={int(old_box[1])}..{int(old_box[3])}->{int(new_box[1])}..{int(new_box[3])}",
            flush=True,
        )
    trace["state"] = state
    trace["next_reason"] = "unknown"
    return state


def _traced_ensure_known_glyph_ownership(context: dict, pairs, models) -> bool:
    changed = _original_ensure_known_glyph_ownership(context, pairs, models)
    trace = context.get("_row_reanalysis_trace")
    if trace is not None:
        trace["next_reason"] = (
            "known-glyph-ownership" if changed else "owner-revision-sync"
        )
    return changed


def _traced_assign_split_components_below_known_extent(context: dict, state: dict):
    records = _original_assign_split_components_below_known_extent(context, state)
    trace = context.get("_row_reanalysis_trace")
    if records and trace is not None:
        trace["next_reason"] = "known-upper-extent"
    return records


# The core editor calls these globals dynamically.  Wrapping them here lets the
# shared scanner expose exactly why its internal second/third row analyses run.
page_editor._load_owned_row_state = _traced_load_owned_row_state
page_editor._ensure_known_glyph_ownership = _traced_ensure_known_glyph_ownership
page_editor._assign_split_components_below_known_extent = _traced_assign_split_components_below_known_extent


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
    set_trace_row(context.get("page_number"), position)
    context["_row_reanalysis_trace"] = {
        "position": tuple(position),
        "attempt": 0,
        "state": None,
        "next_reason": "initial",
    }
    try:
        state = _base_load_review_state_pixel_array(context, position, models)
    finally:
        context.pop("_row_reanalysis_trace", None)
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
