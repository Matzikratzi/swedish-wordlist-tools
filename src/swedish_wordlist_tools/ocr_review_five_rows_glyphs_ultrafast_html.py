from __future__ import annotations

import html

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

# Add a narrowly scoped destructive action to the same editor. Keep references
# to the original renderer and edit handler before monkeypatching so wrappers
# cannot recurse.
_original_render_html = fast.ui.editor.render_html
_original_apply_edit = fast.legacy.apply_edit
fast.ui.editor.render_html = lambda state, message="": render_html_with_delete(
    _original_render_html, state, message
)
fast.legacy.apply_edit = lambda state, facit, form: apply_edit_with_delete(
    _original_apply_edit, state, facit, form
)

# In defect mode the URL can still point at the scan anchor while the editor is
# actually displaying the first defective row found much later on the page.
# The base editor's form has no explicit action, so the browser would POST back
# to that stale anchor row. Make the form submit to the row that is actually
# active in the editor, preserving defect mode and the packet anchor.
_original_five_row_render = fast.ui.render_five_row_html


def render_five_row_html_to_active_row(
    states,
    active_position,
    all_positions,
    message="",
    *,
    mode="all",
    anchor=None,
):
    document = _original_five_row_render(
        states,
        active_position,
        all_positions,
        message,
        mode=mode,
        anchor=anchor,
    )
    packet_anchor = anchor or (states[0]["column"], states[0]["row"])
    action = fast.ui.row_url(active_position, mode=mode, anchor=packet_anchor)
    needle = '<form method="post" id="form">'
    replacement = (
        '<form method="post" id="form" action="'
        + html.escape(action, quote=True)
        + '">'
    )
    if needle not in document:
        raise ValueError("could not find glyph edit form in five-row editor HTML")
    return document.replace(needle, replacement, 1)


fast.ui.render_five_row_html = render_five_row_html_to_active_row


def main() -> int:
    print("review: ULTRAFAST använder grupperad exact-glyphmatchning vid säkra vita gap", flush=True)
    print("review: vald matchad glyph kan raderas ur facit för att delas om", flush=True)
    print("review: glyphändringar POST:as alltid till den faktiskt aktiva raden", flush=True)
    return fast.main()


if __name__ == "__main__":
    raise SystemExit(main())
