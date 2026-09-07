import unittest

from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray, WHITE
from swedish_wordlist_tools.ocr_review_page_pixel_array_glyphs_html import (
    _isolated_above_lower_row,
)


class AutoIsolatedRowOwnershipTest(unittest.TestCase):
    def _context(self, lower_point):
        owners = PagePixelArray(width=20, height=20, data=bytearray([WHITE]) * 400)
        upper_code = owners.row_code(0)
        lower_code = owners.row_code(1)
        for x, y in ((5, 8), (5, 9)):
            owners.data[y * owners.width + x] = upper_code
        owners.data[10 * owners.width + 5] = lower_code
        owners.data[lower_point[1] * owners.width + lower_point[0]] = lower_code
        return {
            "pixel_owners": owners,
            "row_map": {
                "columns": [
                    {
                        "crop_left": 0,
                        "crop_right": 20,
                        "rows": [
                            {"page_top": 2, "page_bottom": 10},
                            {"page_top": 10, "page_bottom": 19},
                        ],
                    }
                ]
            },
        }

    def _candidate(self):
        return {
            "upper_row": 0,
            "lower_row": 1,
            "separator_page_y": 10,
            "component_pixels": [(5, 8), (5, 9), (5, 10)],
            "upper_owned": 2,
            "lower_owned": 1,
        }

    def test_accepts_component_above_lower_row_at_manhattan_six_or_more(self):
        proof = _isolated_above_lower_row(
            self._context((6, 15)), 0, self._candidate(), min_distance=6
        )
        self.assertIsNotNone(proof)
        self.assertEqual(proof["min_manhattan_distance"], 6)
        self.assertEqual(proof["component_bottom"], 10)
        self.assertEqual(proof["lower_row_top_ink"], 15)

    def test_rejects_component_too_close_to_lower_row(self):
        proof = _isolated_above_lower_row(
            self._context((6, 14)), 0, self._candidate(), min_distance=6
        )
        self.assertIsNone(proof)

    def test_rejects_component_that_overlaps_lower_row_vertically(self):
        proof = _isolated_above_lower_row(
            self._context((9, 10)), 0, self._candidate(), min_distance=6
        )
        self.assertIsNone(proof)


if __name__ == "__main__":
    unittest.main()
