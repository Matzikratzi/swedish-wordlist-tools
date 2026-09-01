from __future__ import annotations

from . import ocr_review_five_rows_glyphs_fast_html as fast
from .ocr_glyph_review_delete import apply_edit_with_delete, render_html_with_delete
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


# The fast editor already reuses page geometry, keeps generation-aware row
# state, and prevents duplicate concurrent work. Its remaining hot path is the
# whole-row exact matcher imported into that module as ``analyse_row_exact``.
# Swap only that implementation for the previously verified safe-gap grouped
# matcher. ``load_review_state_fast`` resolves the module global at call time,
# so no other editor behaviour changes.
fast.analyse_row_exact = analyse_row_exact_grouped

# Add a narrowly scoped destructive action to the same editor. Capture both
# original callables before monkeypatching; otherwise the non-delete path would
# call the patched function recursively instead of saving add/relabel edits.
_original_render_html = fast.ui.editor.render_html
_original_apply_edit = fast.legacy.apply_edit
fast.ui.editor.render_html = lambda state, message="": render_html_with_delete(
    _original_render_html, state, message
)
fast.legacy.apply_edit = lambda state, facit, form: apply_edit_with_delete(
    _original_apply_edit, state, facit, form
)


def main() -> int:
    print("review: ULTRAFAST använder grupperad exact-glyphmatchning vid säkra vita gap", flush=True)
    print("review: vald matchad glyph kan raderas ur facit för att delas om", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
