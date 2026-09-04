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


def load_review_state_pixel_array(context, position, models):
    # The merge probe uses exactly the same analyser as the ordinary row loader.
    context["analyse_row_exact"] = page_editor.fast.analyse_row_exact
    state = _base_load_review_state_pixel_array(context, position, models)
    if state.get("fully_exact"):
        return state

    # First handle the established case where the current row is itself the
    # lower row and a known disconnected glyph can reclaim pixels from above.
    records = repair_lower_row_disconnected_glyphs(context, state, models)
    if records:
        state = _base_load_review_state_pixel_array(context, position, models)
        state["disconnected_glyph_ownership"] = records
        if state.get("fully_exact"):
            return state

    # A physical row containing ink but *no* exact glyph match can be a false
    # segmentation row made only from detached dots/diacritics.  Probe the row
    # together with the following physical row without mutating ownership.  We
    # accept only a complete pixel-perfect cover on one common baseline.
    if int(state.get("source_pixels") or 0) > 0 and not state.get("matches"):
        column, row_index = map(int, position)
        columns = context.get("row_map", {}).get("columns") or []
        rows = columns[column].get("rows") or [] if 0 <= column < len(columns) else []
        if row_index + 1 < len(rows):
            lower_position = (column, row_index + 1)
            lower_state = _base_load_review_state_pixel_array(context, lower_position, models)
            proof = probe_zero_match_merge_down(context, state, lower_state, models)
            if proof is not None:
                moved = apply_merge_down(context, proof)
                if moved:
                    if not context.get("quiet_successful_ownership"):
                        print(
                            f"review: provmerge c{column} r{row_index}/{row_index + 1}: "
                            f"{proof['source_pixels']}/{proof['source_pixels']} px exakt på en baseline; "
                            f"flyttade {moved} px nedåt, text={proof['labels']!r}",
                            flush=True,
                        )
                    state = _base_load_review_state_pixel_array(context, position, models)
                    state = _mark_absorbed_empty(state, proof)
                    return state

    return state


build_page_context_pixel_array = page_editor.build_page_context_pixel_array
