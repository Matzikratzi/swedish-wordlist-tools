import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray
from swedish_wordlist_tools.ocr_pair_separator import (
    apply_cut_bidirectional,
    candidate_separator_tiers,
    restore_changed_ownership,
)
from swedish_wordlist_tools.ocr_refine_known_glyph_ownership import (
    refine_known_glyph_ownership,
)


class PairSeparatorTests(unittest.TestCase):
    def test_disconnected_cut_can_move_ownership_both_ways_and_restore(self):
        image = Image.new("L", (8, 10), 255)
        image.putpixel((2, 3), 0)
        image.putpixel((2, 4), 0)
        image.putpixel((5, 6), 0)
        image.putpixel((5, 7), 0)
        owners = PagePixelArray.from_image(image)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 8,
                    "crop_left": 0,
                    "crop_right": 8,
                    "rows": [
                        {"page_top": 0, "page_bottom": 4},
                        {"page_top": 4, "page_bottom": 10},
                    ],
                }
            ]
        }
        owners.assign_row_map(row_map)
        upper = PagePixelArray.row_code(0)
        lower = PagePixelArray.row_code(1)

        tiers = candidate_separator_tiers(
            owners,
            upper_code=upper,
            lower_code=lower,
            boundary=4,
            left=0,
            right=8,
            radius=3,
        )
        cuts = {y for _name, values in tiers for y in values}
        self.assertIn(5, cuts)

        before = bytes(owners.data)
        changed = apply_cut_bidirectional(
            owners,
            upper_code=upper,
            lower_code=lower,
            cut_y=5,
            boundary=4,
            left=0,
            right=8,
            radius=3,
        )
        self.assertEqual(owners.value(2, 4), upper)
        self.assertTrue(changed)
        restore_changed_ownership(owners, changed)
        self.assertEqual(bytes(owners.data), before)

    def test_refine_uses_fast_horizontal_separator_for_wrong_boundary(self):
        page = Image.new("L", (24, 20), 255)
        upper_model = GlyphModel(
            "U",
            "roman",
            frozenset({(0, -2), (0, -1), (0, 0)}),
            1,
        )
        lower_model = GlyphModel(
            "L",
            "roman",
            frozenset({(0, -3), (0, -2), (0, -1), (0, 0)}),
            1,
        )
        models = [upper_model, lower_model]

        for x, y in upper_model.pixels:
            page.putpixel((3 + x, 10 + y), 0)
        for x, y in lower_model.pixels:
            page.putpixel((14 + x, 15 + y), 0)

        # The nominal boundary is one line too high: the last U pixel at y=10
        # is initially owned by the lower row. There is nevertheless a clean
        # horizontal separator below U and above L.
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 24,
                    "crop_left": 0,
                    "crop_right": 24,
                    "rows": [
                        {"page_top": 6, "page_bottom": 10},
                        {"page_top": 10, "page_bottom": 19},
                    ],
                }
            ]
        }
        owners = PagePixelArray.from_image(page)
        owners.assign_row_map(row_map)
        upper = PagePixelArray.row_code(0)
        lower = PagePixelArray.row_code(1)
        self.assertEqual(owners.value(3, 10), lower)

        changes = refine_known_glyph_ownership(page, row_map, owners, models)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["evidence_mode"], "fast-horizontal-separator")
        self.assertIn(
            changes[0]["separator_strategy"],
            {"white-band", "8-disconnected", "owned-extrema", "legacy-bounded"},
        )
        self.assertEqual(changes[0]["moved_to_upper"], 1)
        self.assertEqual(changes[0]["moved_to_lower"], 0)
        self.assertEqual(owners.value(3, 10), upper)


if __name__ == "__main__":
    unittest.main()
