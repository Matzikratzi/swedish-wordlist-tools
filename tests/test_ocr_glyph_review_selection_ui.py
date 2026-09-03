import unittest
from types import SimpleNamespace

from swedish_wordlist_tools import ocr_review_row_glyphs_html as legacy
from swedish_wordlist_tools.ocr_glyph_review_delete import _RoleWithTypography


class GlyphReviewSelectionUiTests(unittest.TestCase):
    def test_review_html_styles_and_constrains_selection(self):
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

        html = legacy.render_html(state)

        self.assertIn(".chip.italic .glyph-label{font-style:italic", html)
        self.assertIn(".pixel-unit{display:block", html)
        self.assertIn("unit.textContent='px'", html)
        self.assertIn('"points": [[1, 4], [1, 5]]', html)
        self.assertIn("function selectionValid(itemIds,pixelKeys)", html)
        self.assertIn("function itemsContiguous(ids)", html)
        self.assertIn("function connected8(keys)", html)
        self.assertIn("if(!setsTouch8(itemKeys,pixelKeys))return false", html)
        self.assertIn("e.key!=='ArrowLeft'&&e.key!=='ArrowRight'", html)
        self.assertIn("replaceSet(chosen,new Set([target.id]))", html)


if __name__ == "__main__":
    unittest.main()
