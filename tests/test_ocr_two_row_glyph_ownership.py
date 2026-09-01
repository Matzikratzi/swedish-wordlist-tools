from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_two_row_glyph_ownership import (
    _vertical_order_ok,
    split_touching_neighbor_glyphs,
)


class TwoRowGlyphOwnershipTests(unittest.TestCase):
    def test_touching_rows_preserve_vertical_order(self) -> None:
        current = frozenset({(2, 3), (3, 4), (4, 5)})
        below_touching = frozenset({(5, 5), (5, 6), (6, 7)})
        below_crossing = frozenset({(5, 4), (5, 6), (6, 7)})
        above_touching = frozenset({(1, 1), (1, 2), (2, 3)})
        self.assertTrue(_vertical_order_ok(current, below_touching, neighbor_is_below=True))
        self.assertFalse(_vertical_order_ok(current, below_crossing, neighbor_is_below=True))
        self.assertTrue(_vertical_order_ok(current, above_touching, neighbor_is_below=False))

    def test_exact_known_glyphs_touching_across_rows_are_split(self) -> None:
        image = Image.new("L", (12, 12), 255)
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
        box = (0, 0, 10, 6)
        crop = image.crop(box)

        cleaned, removed, diagnostics = split_touching_neighbor_glyphs(
            image, row_map, 0, 0, box, crop, models
        )

        self.assertEqual(removed, 1)
        self.assertEqual(cleaned.getpixel((3, 5)), 255)
        self.assertEqual(cleaned.getpixel((3, 4)), 0)
        split = next(row for row in diagnostics if row["status"] == "split")
        self.assertEqual(split["current_labels"], "]")
        self.assertEqual(split["neighbor_labels"], "l")
        self.assertEqual(split["vertical_order"], "touch-or-gap")

    def test_unknown_neighbor_shape_is_not_cut(self) -> None:
        image = Image.new("L", (12, 12), 255)
        upper_page = {(2, 2), (3, 2), (3, 3), (3, 4)}
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
            image, row_map, 0, 0, box, crop, models
        )

        self.assertEqual(removed, 0)
        self.assertEqual(cleaned.getpixel((3, 5)), 0)
        self.assertFalse(any(row["status"] == "split" for row in diagnostics))


if __name__ == "__main__":
    unittest.main()
