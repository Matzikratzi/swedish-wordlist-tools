import unittest

from swedish_wordlist_tools.ocr_review_row_glyphs_paint_html import render_html


class FreehandGlyphEditorHtmlTests(unittest.TestCase):
    def test_render_html_uses_freehand_mask_not_drag_rectangle(self):
        state = {
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
        html = render_html(state)
        self.assertIn("Frihandsmask", html)
        self.assertIn("function paintLine", html)
        self.assertIn("function paintPoint", html)
        self.assertIn("Endast svarta källpixlar kan väljas", html)
        self.assertIn("selectedBounds", html)
        self.assertNotIn("dragStart", html)
        self.assertNotIn("strokeRect(x,y,w,h);}}\n}}\nfunction sync", html)

    def test_alt_is_erase_and_brush_sizes_are_available(self):
        state = {
            "page": 1,
            "column": 0,
            "row": 1,
            "covered_pixels": 0,
            "source_pixels": 1,
            "removed_neighbor_pixels": 0,
            "text": "",
            "crop_width": 2,
            "crop_height": 2,
            "baseline": 1,
            "image": "data:image/png;base64,AA==",
            "source_ink_points": [[0, 0]],
            "items": [],
        }
        html = render_html(state)
        self.assertIn("erase=e.altKey", html)
        self.assertIn("3×3", html)
        self.assertIn("5×5", html)


if __name__ == "__main__":
    unittest.main()
