from __future__ import annotations

"""Shared page-pixel review path used by both scanners and review editors.

All automatic row-ownership repair belongs here so batch classification and
interactive review see the same state.
"""

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs
from .ocr_probe_merge_with_lower_row import apply_merge_down, probe_zero_match_merge_down


_base_load_review_state_pixel_array = page_editor.load_review_state_pixel_array


def _mark_absorbed_empty(state: dict, proof: dict) -> dict:
    """An emptied segmentation artefact is complete, not a review defect."""
    out = dict(state)
    if int(out.get("source_pixels") or 0) == 0:
        out["fully_exact"] = True
        out["row_absorbed_by_lower"] = proof
    return out


def _probe_merge_down_if_zero_match(context, position, state, models):
    """Probe the following row only for the narrow zero-match artefact case."""
    if int(state.get("source_pixels") or 0) <= 0 or state.get("matches"):
        return None

    column, row_index = map(int, position)
    columns = context.get("row_map", {}).get("columns") or []
    rows = columns[column].get("rows") or [] if 0 <= column < len(columns) else []
    if row_index + 1 >= len(rows):
        return None

    lower_position = (column, row_index + 1)
    lower_state = _base_load_review_state_pixel_array(context, lower_position, models)
    return probe_zero_match_merge_down(context, state, lower_state, models)


def load_review_state_pixel_array(context, position, models):
    state = _base_load_review_state_pixel_array(context, position, models)
    if state.get("fully_exact"):
        return state

    # Most rows stop here.  Looking at the following row is allowed only for a
    # physical row that contains ink but has *zero* accepted glyph matches.
    # This keeps merge probing a rare fallback rather than normal OCR work.
    if int(state.get("source_pixels") or 0) > 0 and not state.get("matches"):
        context["analyse_row_exact"] = page_editor.fast.analyse_row_exact
        proof = _probe_merge_down_if_zero_match(context, position, state, models)
        if proof is not None:
            moved = apply_merge_down(context, proof)
            if moved:
                column, row_index = map(int, position)
                if not context.get("quiet_successful_ownership"):
                    print(
                        f"review: provmerge c{column} r{row_index}/{row_index + 1}: "
                        f"täckning {proof['lower_covered_pixels']}→{proof['covered_pixels']} px; "
                        f"flyttade {moved} px nedåt, text={proof['labels']!r}",
                        flush=True,
                    )
                state = _base_load_review_state_pixel_array(context, position, models)
                state = _mark_absorbed_empty(state, proof)
                return state

    # Only unresolved rows reach the more expensive exact disconnected-glyph
    # ownership repair.  This path scans facit geometry and must not run merely
    # as preparation for a merge probe.
    records = repair_lower_row_disconnected_glyphs(context, state, models)
    if records:
        state = _base_load_review_state_pixel_array(context, position, models)
        state["disconnected_glyph_ownership"] = records

    return state


build_page_context_pixel_array = page_editor.build_page_context_pixel_array
