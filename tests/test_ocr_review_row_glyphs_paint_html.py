import unittest

from swedish_wordlist_tools.ocr_review_row_glyphs_paint_html import render_html


class HybridGlyphEditorHtmlTests(unittest.TestCase):
    def _state(self):
        return {
            "page": 1,
            "column": 0,
            "row": 1,
            "covered_pixels": 10,
            "source_pixels": 12,
            "removed_neighbor_pixels": 0,
            "text": "a",
            "crop_width": 20,
            "crop_height": 10,
            "baseline": 7,
            "image": "data:image/png;base64,AA==",
            "source_ink_points": [[1, 1], [2, 2]],
            "items": [],
        }

    def test_rectangle_is_primary_selection(self):
        html = render_html(self._state())
        self.assertIn("Hybridmarkering", html)
        self.assertIn("function addRectangle", html)
        self.assertIn("dragStart", html)
        self.assertIn("dra en rektangel", html)
        self.assertNotIn("function paintLine", html)
        self.assertNotIn("Pensel", html)

    def test_shift_adds_and_alt_removes_single_pixels(self):
        html = render_html(self._state())
        self.assertIn("e.shiftKey", html)
        self.assertIn("touchPixel(p,'add')", html)
        self.assertIn("e.altKey", html)
        self.assertIn("touchPixel(p,'remove')", html)
        self.assertIn("Shift-klick", html)
        self.assertIn("Alt-klick", html)

    def test_only_source_ink_can_be_touched(self):
        html = render_html(self._state())
        self.assertIn("if(!sourceInk.has(key))return", html)
        self.assertIn("selectedBounds", html)


if __name__ == "__main__":
    unittest.main()
