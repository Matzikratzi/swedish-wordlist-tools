from __future__ import annotations

"""Backward-compatible entry point for the unified three-row glyph editor.

Queue mode deliberately keeps the active edit canvas in the exact coordinate
system of the analysed row.  The unified navigator can add a small source strip
on the left for visual context, but shifting the edit canvas with that strip
makes POSTed pixel coordinates differ from the state passed to ``apply_edit``.
That is especially visible when combining existing glyph matches and residual
pixels into one cluster glyph.

This wrapper also preserves the active queue row after a failed POST instead of
falling back to the first queue entry.
"""

import threading

from . import ocr_review_page_pixel_array_navigator_html as navigator


_post_context = threading.local()
_installed = False


def _install_queue_safety() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    # Keep display/edit coordinates identical.  Context is still shown in the
    # three row raster and in the queue cards, so the extra two-column strip is
    # not needed on the actual editable canvas.
    navigator._fine_display_state = lambda _context, state, *, extra_left=2: state

    original_apply_edit = navigator.page_editor.fast.legacy.apply_edit
    original_url = navigator._url

    def apply_edit_remembering_failed_row(state, facit, form):
        position = (int(state["page"]), int(state["column"]), int(state["row"]))
        try:
            return original_apply_edit(state, facit, form)
        except Exception:
            _post_context.failed_position = position
            raise

    def url_preserving_failed_row(position, *, nav):
        failed = getattr(_post_context, "failed_position", None)
        if failed is not None:
            del _post_context.failed_position
            return original_url(failed, nav=nav)
        return original_url(position, nav=nav)

    navigator.page_editor.fast.legacy.apply_edit = apply_edit_remembering_failed_row
    navigator._url = url_preserving_failed_row


def main() -> int:
    _install_queue_safety()
    return navigator.main()


if __name__ == "__main__":
    raise SystemExit(main())
