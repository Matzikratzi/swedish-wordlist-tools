import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray
from swedish_wordlist_tools.ocr_pair_separator import (
    apply_cut_bidirectional,
    candidate_separator_tiers,
    restore_changed_ownership,
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


if __name__ == "__main__":
    unittest.main()
