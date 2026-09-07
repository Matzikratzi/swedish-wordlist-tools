from __future__ import annotations

import unittest

from swedish_wordlist_tools import ocr_review_page_pixel_array_navigator_html as navigator
from swedish_wordlist_tools import ocr_review_page_pixel_array_queue_html as queue_editor


class QueueEditorSaveSafetyTests(unittest.TestCase):
    def test_edit_canvas_keeps_original_coordinates(self):
        original_fine = navigator._fine_display_state
        original_apply = navigator.page_editor.fast.legacy.apply_edit
        original_url = navigator._url
        installed = queue_editor._installed
        try:
            queue_editor._installed = False
            queue_editor._install_queue_safety()
            state = {"page": 34, "column": 1, "row": 32, "crop_box": (247, 645, 456, 666)}
            self.assertIs(navigator._fine_display_state({}, state, extra_left=2), state)
        finally:
            navigator._fine_display_state = original_fine
            navigator.page_editor.fast.legacy.apply_edit = original_apply
            navigator._url = original_url
            queue_editor._installed = installed

    def test_failed_save_redirects_to_posted_queue_row(self):
        original_fine = navigator._fine_display_state
        original_apply = navigator.page_editor.fast.legacy.apply_edit
        original_url = navigator._url
        installed = queue_editor._installed
        try:
            def failing_apply(_state, _facit, _form):
                raise ValueError("boom")

            navigator.page_editor.fast.legacy.apply_edit = failing_apply
            navigator._url = lambda position, *, nav: f"/{position[0]}/{position[1]}/{position[2]}/{nav}"
            queue_editor._installed = False
            queue_editor._install_queue_safety()

            state = {"page": 34, "column": 1, "row": 32}
            with self.assertRaisesRegex(ValueError, "boom"):
                navigator.page_editor.fast.legacy.apply_edit(state, None, {})

            # The navigator's exception path asks for its initial row.  Queue
            # safety must substitute the row whose POST actually failed.
            self.assertEqual(
                navigator._url((33, 0, 6), nav="queue"),
                "/34/1/32/queue",
            )
            # The remembered redirect is one-shot.
            self.assertEqual(
                navigator._url((33, 0, 6), nav="queue"),
                "/33/0/6/queue",
            )
        finally:
            navigator._fine_display_state = original_fine
            navigator.page_editor.fast.legacy.apply_edit = original_apply
            navigator._url = original_url
            queue_editor._installed = installed
            if hasattr(queue_editor._post_context, "failed_position"):
                del queue_editor._post_context.failed_position


if __name__ == "__main__":
    unittest.main()
