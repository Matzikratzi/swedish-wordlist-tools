import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_refine_row_boundaries import (
    _boundary_bridge_count,
    refine_row_boundaries_by_connectivity,
)


class RefineRowBoundariesTests(unittest.TestCase):
    def test_boundary_moves_below_upper_descender_instead_of_cutting_it(self):
        page = Image.new("L", (40, 40), 255)

        # Upper row body plus a descender that continues through the old split.
        for y in range(7, 17):
            page.putpixel((10, y), 0)
        for x in range(7, 14):
            page.putpixel((x, 10), 0)

        # Lower row begins after the descender; no component crosses y=17.
        for y in range(18, 26):
            page.putpixel((25, y), 0)
        for x in range(22, 29):
            page.putpixel((x, 20), 0)

        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 40,
                    "crop_left": 0,
                    "crop_right": 40,
                    "rows": [
                        {"page_top": 7, "page_bottom": 15, "center_y": 10.5},
                        {"page_top": 15, "page_bottom": 26, "center_y": 20.0},
                    ],
                }
            ]
        }

        self.assertGreater(
            _boundary_bridge_count(page, y=15, left=0, right=40),
            0,
        )
        self.assertEqual(
            _boundary_bridge_count(page, y=17, left=0, right=40),
            0,
        )

        changes = refine_row_boundaries_by_connectivity(page, row_map)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["old_boundary"], 15)
        self.assertEqual(changes[0]["new_boundary"], 17)
        self.assertEqual(row_map["columns"][0]["rows"][0]["page_bottom"], 17)
        self.assertEqual(row_map["columns"][0]["rows"][1]["page_top"], 17)

    def test_zero_bridge_boundary_is_left_untouched(self):
        page = Image.new("L", (30, 30), 255)
        for y in range(5, 12):
            page.putpixel((8, y), 0)
        for y in range(16, 23):
            page.putpixel((20, y), 0)
        row_map = {
            "columns": [
                {
                    "left": 0,
                    "right": 30,
                    "rows": [
                        {"page_top": 5, "page_bottom": 14, "center_y": 9.0},
                        {"page_top": 14, "page_bottom": 23, "center_y": 18.0},
                    ],
                }
            ]
        }

        changes = refine_row_boundaries_by_connectivity(page, row_map)

        self.assertEqual(changes, [])
        self.assertEqual(row_map["columns"][0]["rows"][0]["page_bottom"], 14)
        self.assertEqual(row_map["columns"][0]["rows"][1]["page_top"], 14)


if __name__ == "__main__":
    unittest.main()
