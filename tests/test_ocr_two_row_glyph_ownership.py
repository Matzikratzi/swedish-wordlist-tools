from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_two_row_glyph_ownership import split_touching_neighbor_glyphs


class TwoRowGlyphOwnershipTests(unittest.TestCase):
    def test_exact_known_glyphs_touching_across_rows_are_split(self) -> None:
        image = Image.new("L", (12, 12), 255)
        # Upper glyph: baseline y=4. Lower glyph: baseline y=5. They touch
        # vertically at x=3 between y=4 and y=5, making one 8-connected blob.
        upper_page = {(2, 2), (3, 2), (3, 3), (3, 4)}
        lower_page = {(3, 5), (3, 6), (3, 7), (4, 7)}
        for point in upper_page | lower_page:
            image.putpixel(point, 0)

        models = [
            GlyphModel(
                label="]",
                style="roman",
                pixels=frozenset({(0, -2), (1, -2), (1, -1), (1, 0)}),
                sources=2,
            ),
            GlyphModel(
                label="l",
                style="roman",
                pixels=frozenset({(0, 0), (0, 1), (0, 2), (1, 2)}),
                sources=2,
            ),
        ]
        row_map = {
            "columns": [
                {
                    "rows": [
                        {"page_top": 1, "page_bottom": 5},
                        {"page_top": 5, "page_bottom": 9},
                    ]
                }
            ]
        }
        box = (0, 0, 10, 6)  # target row plus one pixel of the row below
        crop = image.crop(box)

        cleaned, removed, diagnostics = split_touching_neighbor_glyphs(
            image,
            row_map,
            0,
            0,
            box,
            crop,
            models,
        )

        self.assertEqual(removed, 1)
        self.assertEqual(cleaned.getpixel((3, 5)), 255)
        self.assertEqual(cleaned.getpixel((3, 4)), 0)
        self.assertTrue(any(row["status"] == "split" for row in diagnostics))
        split = next(row for row in diagnostics if row["status"] == "split")
        self.assertEqual(split["current_labels"], "]")
        self.assertEqual(split["neighbor_labels"], "l")

    def test_unknown_neighbor_shape_is_not_cut(self) -> None:
        image = Image.new("L", (12, 12), 255)
        upper_page = {(2, 2), (3, 2), (3, 3), (3, 4)}
        # This lower blob is not explained by any known model.
        lower_page = {(3, 5), (3, 6), (4, 6), (5, 6), (5, 7)}
        for point in upper_page | lower_page:
            image.putpixel(point, 0)
        models = [
            GlyphModel(
                label="]",
                style="roman",
                pixels=frozenset({(0, -2), (1, -2), (1, -1), (1, 0)}),
                sources=2,
            )
        ]
        row_map = {
            "columns": [
                {
                    "rows": [
                        {"page_top": 1, "page_bottom": 5},
                        {"page_top": 5, "page_bottom": 9},
                    ]
                }
            ]
        }
        box = (0, 0, 10, 6)
        crop = image.crop(box)

        cleaned, removed, diagnostics = split_touching_neighbor_glyphs(
            image,
            row_map,
            0,
            0,
            box,
            crop,
            models,
        )

        self.assertEqual(removed, 0)
        self.assertEqual(cleaned.getpixel((3, 5)), 0)
        self.assertFalse(any(row["status"] == "split" for row in diagnostics))


if __name__ == "__main__":
    unittest.main()
