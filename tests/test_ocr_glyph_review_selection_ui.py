import unittest
from types import SimpleNamespace

from PIL import Image

from swedish_wordlist_tools import ocr_review_row_glyphs_paint_html as paint
from swedish_wordlist_tools.ocr_glyph_review_delete import (
    _RoleWithTypography,
    render_html_with_delete,
)
from swedish_wordlist_tools.ocr_neighbor_row_raster import (
    _column_review_left,
    _compact_review_state,
    _decorate_review_html,
)


class GlyphReviewSelectionUiTests(unittest.TestCase):
    def test_review_html_styles_pixels_arrows_and_canvas_labels(self):
        style = _RoleWithTypography("unknown", "italic", False)
        match = SimpleNamespace(
            label="a",
            style=style,
            baseline=5,
            pixels=frozenset({(1, 4), (1, 5)}),
        )
        state = {
            "page": 2,
            "column": 1,
            "row": 37,
            "covered_pixels": 2,
            "source_pixels": 3,
            "removed_neighbor_pixels": 0,
            "text": "a",
            "image": "data:image/png;base64,",
            "crop_width": 8,
            "crop_height": 8,
            "baseline": 5,
            "source_ink_points": [[1, 4], [1, 5], [3, 5]],
            "items": [
                {
                    "id": "M00",
                    "kind": "match",
                    "label": "a",
                    "style": style,
                    "pixels": 2,
                    "bbox": {"left": 1, "top": 4, "right": 2, "bottom": 6},
                },
                {
                    "id": "U00",
                    "kind": "residual",
                    "label": "?",
                    "style": "unknown",
                    "pixels": 1,
                    "bbox": {"left": 3, "top": 5, "right": 4, "bottom": 6},
                },
            ],
            "point_sets": {
                "M00": frozenset({(1, 4), (1, 5)}),
                "U00": frozenset({(3, 5)}),
            },
            "matches": [match],
        }

        html = _decorate_review_html(
            lambda current_state, message="": render_html_with_delete(
                paint.render_html, current_state, message
            ),
            state,
        )

        self.assertIn(".chip.italic .glyph-label{font-style:italic", html)
        self.assertIn(".pixel-unit{display:block", html)
        self.assertIn("unit.textContent='px'", html)
        self.assertNotIn("function selectionValid(itemIds,pixelKeys)", html)
        self.assertNotIn("function itemsContiguous(ids)", html)
        self.assertNotIn("function connected8(keys)", html)
        self.assertNotIn("setsTouch8", html)
        self.assertIn("e.key!=='ArrowLeft'&&e.key!=='ArrowRight'", html)
        self.assertIn("replaceSet(chosen,new Set([target.id]))", html)
        self.assertIn("topPad=4, bottomPad=20", html)
        self.assertIn("it.kind!=='match' || it.reviewed===false", html)
        self.assertIn("let labelRight=-Infinity", html)
        self.assertIn("const wanted=x", html)
        self.assertIn("Math.max(wanted,labelRight+2)", html)
        self.assertIn("labelRight=lx+tw", html)
        self.assertIn("y+h+15", html)
        self.assertIn("#ff5a00", html)

    def test_column_crop_ignores_left_furniture_and_keeps_homonym_margin(self):
        image = Image.new("L", (120, 60), 255)
        rows = []
        # x=2 simulates the far-left column furniture that fooled the first
        # implementation. Most lexical rows start at headword x=59; one row has
        # a superscript homonym at x=51 and one continuation starts at x=70.
        starts = [59, 59, 59, 59, 51, 70]
        for index, x in enumerate(starts):
            top = index * 10
            rows.append({"page_top": top, "page_bottom": top + 8})
            image.putpixel((2, top + 3), 0)
            image.putpixel((x, top + 3), 0)
        context = {
            "page": image,
            "pixel_gray_page": image,
            "threshold": 210,
            "row_map": {
                "columns": [{"crop_left": 0, "crop_right": 120, "rows": rows}]
            },
        }

        self.assertEqual(_column_review_left(context, 0), 44)
        self.assertEqual(_column_review_left(context, 0), 44)
        self.assertEqual(context["review_headword_anchors"][0], 59)

        state = {
            "column": 0,
            "row": 0,
            "crop_box": (0, 0, 120, 8),
            "crop_width": 120,
            "source_ink_points": [[51, 3], [59, 3]],
            "point_sets": {"M00": frozenset({(51, 3)}), "M01": frozenset({(59, 3)})},
            "items": [
                {"id": "M00", "bbox": {"left": 51, "top": 3, "right": 52, "bottom": 4}},
                {"id": "M01", "bbox": {"left": 59, "top": 3, "right": 60, "bottom": 4}},
            ],
        }
        compact = _compact_review_state(context, state)
        self.assertEqual(compact["crop_box"], (44, 0, 120, 8))
        self.assertEqual(compact["crop_width"], 76)
        self.assertEqual(compact["source_ink_points"], [[7, 3], [15, 3]])
        self.assertEqual(compact["items"][0]["bbox"]["left"], 7)
        self.assertEqual(compact["items"][1]["bbox"]["left"], 15)


if __name__ == "__main__":
    unittest.main()
