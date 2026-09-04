from __future__ import annotations

"""Shared page-pixel review path used by both scanners and review editors.

This wrapper adds the disconnected-glyph ownership repair to the ordinary
page-wide byte-array review state. Callers should use this function instead of
calling the raw page-editor loader directly so batch classification and
interactive review see the same ownership state.
"""

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_disconnected_glyph_ownership import repair_lower_row_disconnected_glyphs


_base_load_review_state_pixel_array = page_editor.load_review_state_pixel_array


def load_review_state_pixel_array(context, position, models):
    state = _base_load_review_state_pixel_array(context, position, models)
    if state.get("fully_exact"):
        return state

    records = repair_lower_row_disconnected_glyphs(context, state, models)
    if not records:
        return state

    state = _base_load_review_state_pixel_array(context, position, models)
    state["disconnected_glyph_ownership"] = records
    return state


build_page_context_pixel_array = page_editor.build_page_context_pixel_array
