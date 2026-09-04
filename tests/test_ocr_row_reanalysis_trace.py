from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from swedish_wordlist_tools import ocr_review_page_pixel_array_shared as shared


class RowReanalysisTraceTests(unittest.TestCase):
    def test_state_page_ink_uses_page_coordinates(self):
        state = {
            "crop_box": (100, 20, 140, 40),
            "source_ink_points": [[2, 3], [5, 7]],
        }
        self.assertEqual(shared._state_page_ink(state), {(102, 23), (105, 27)})

    def test_second_attempt_reports_only_changed_x_damage(self):
        states = iter(
            [
                {
                    "crop_box": (100, 20, 140, 40),
                    "source_ink_points": [[2, 3], [5, 7]],
                    "pixel_owner_revision": 3,
                    "pixel_owner_row_revision": 1,
                },
                {
                    "crop_box": (100, 20, 140, 40),
                    "source_ink_points": [[2, 3], [8, 7]],
                    "pixel_owner_revision": 4,
                    "pixel_owner_row_revision": 2,
                },
            ]
        )
        original = shared._original_load_owned_row_state
        shared._original_load_owned_row_state = lambda _context, _position, _models: next(states)
        context = {
            "page_number": 9,
            "_row_reanalysis_trace": {
                "position": (1, 7),
                "attempt": 0,
                "state": None,
                "next_reason": "initial",
            },
        }
        try:
            shared._traced_load_owned_row_state(context, (1, 7), [])
            context["_row_reanalysis_trace"]["next_reason"] = "known-glyph-ownership"
            out = io.StringIO()
            with redirect_stdout(out):
                shared._traced_load_owned_row_state(context, (1, 7), [])
        finally:
            shared._original_load_owned_row_state = original

        text = out.getvalue()
        self.assertIn("attempt=2", text)
        self.assertIn("reason=known-glyph-ownership", text)
        self.assertIn("revision=3->4", text)
        self.assertIn("row_revision=1->2", text)
        self.assertIn("changed_px=2", text)
        self.assertIn("changed_x=105..108", text)


if __name__ == "__main__":
    unittest.main()
