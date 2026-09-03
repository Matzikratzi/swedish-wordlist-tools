import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray
from swedish_wordlist_tools.ocr_refine_known_glyph_ownership import (
    refine_known_glyph_ownership,
)


class RefineKnownGlyphOwnershipTests(unittest.TestCase):
    def test_known_descender_and_ascender_claim_pixels_across_row_boundary(self):
        page = Image.new("L", (30, 24), 255)

        models = [
            GlyphModel(
                "A",
                "roman",
                frozenset({(0, -2), (1, -2), (0, -1), (1, -1), (0, 0), (1, 0)}),
                1,
            ),
            GlyphModel(
                "g",
                "roman",
                frozenset({(0, -2), (0, -1), (0, 0), (0, 1), (1, 2)}),
                1,
            ),
            GlyphModel(
                "b",
                "roman",
                frozenset({(0, -8), (0, -7), (0, -6), (0, -5), (0, -4), (0, -3), (0, -2), (0, -1), (0, 0), (1, 0)}),
                1,
            ),
            GlyphModel(
                "C",
                "roman",
                frozenset({(0, -2), (1, -2), (2, -2), (0, -1), (0, 0), (1, 0), (2, 0)}),
                1,
            ),
        ]

        def draw(model, x0, baseline):
            for x, y in model.pixels:
                page.putpixel((x0 + x, baseline + y), 0)

        draw(models[0], 2, 10)   # upper-row baseline evidence
        draw(models[1], 8, 10)   # g descends through y=12
        draw(models[2], 10, 18)  # b ascends above y=12 and touches g
        draw(models[3], 20, 18)  # lower-row baseline evidence

        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 30,
                    "crop_left": 0,
                    "crop_right": 30,
                    "rows": [
                        {"page_top": 6, "page_bottom": 12},
                        {"page_top": 12, "page_bottom": 21},
                    ],
                }
            ]
        }
        owners = PagePixelArray.from_image(page)
        owners.assign_row_map(row_map)

        upper = PagePixelArray.row_code(0)
        lower = PagePixelArray.row_code(1)
        self.assertEqual(owners.value(9, 12), lower)  # g wrongly below cut
        self.assertEqual(owners.value(10, 10), upper)  # b wrongly above cut
        self.assertEqual(owners.value(10, 11), upper)

        changes = refine_known_glyph_ownership(page, row_map, owners, models)

        self.assertEqual(len(changes), 1)
        self.assertIn("g", changes[0]["upper_labels"])
        self.assertIn("b", changes[0]["lower_labels"])
        self.assertEqual(changes[0]["conflict_pixels"], 0)
        self.assertEqual(owners.value(9, 12), upper)
        self.assertEqual(owners.value(10, 10), lower)
        self.assertEqual(owners.value(10, 11), lower)


if __name__ == "__main__":
    unittest.main()
