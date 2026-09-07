from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_blank_row_boundary import find_blank_row_boundary


class BlankRowBoundaryTests(unittest.TestCase):
    def _row_map(self, boundary: int = 8) -> dict:
        return {
            "columns": [
                {
                    "column": 0,
                    "left": 0,
                    "right": 20,
                    "rows": [
                        {"index": 0, "page_top": 0, "page_bottom": boundary, "center_y": 3.5},
                        {"index": 1, "page_top": boundary, "page_bottom": 16, "center_y": 11.5},
                    ],
                }
            ]
        }

    def test_full_width_white_row_moves_cut_without_glyph_evidence(self) -> None:
        image = Image.new("L", (20, 16), 255)
        # Upper ink reaches y=8. y=9 is fully white. Unknown lower-row ink
        # starts at y=10. No glyph models are involved in this proof.
        for x, y in {(2, 6), (2, 7), (2, 8), (10, 10), (10, 11), (11, 11)}:
            image.putpixel((x, y), 0)

        correction = find_blank_row_boundary(
            image,
            self._row_map(boundary=8),
            0,
            0,
            threshold=210,
            max_shift=4,
            page_number=3,
        )

        self.assertIsNotNone(correction)
        self.assertEqual(correction["status"], "accepted-blank-row-horizontal-boundary")
        self.assertEqual(correction["blank_row_top"], 9)
        self.assertEqual(correction["blank_row_bottom"], 9)
        self.assertEqual(correction["corrected_boundary"], 10)
        self.assertEqual(correction["shift"], 2)

    def test_contiguous_white_band_cuts_after_first_white_row(self) -> None:
        image = Image.new("L", (20, 18), 255)
        for x, y in {(2, 6), (2, 7), (2, 8), (10, 12), (10, 13)}:
            image.putpixel((x, y), 0)
        row_map = self._row_map(boundary=9)
        row_map["columns"][0]["rows"][1]["page_bottom"] = 18

        correction = find_blank_row_boundary(image, row_map, 0, 0, max_shift=4)

        self.assertIsNotNone(correction)
        self.assertEqual((correction["blank_row_top"], correction["blank_row_bottom"]), (9, 11))
        self.assertEqual(correction["corrected_boundary"], 10)

    def test_physical_gap_uses_upper_separator_before_isolated_lower_dot(self) -> None:
        image = Image.new("L", (20, 20), 255)
        # Upper line ends at y=7. The preliminary geometry leaves y=8..13
        # unowned. y=8..9 are white, y=10..11 are an isolated lower-row dot,
        # and y=12..13 are white again before the lower glyph body at y=14.
        for x, y in {(2, 6), (2, 7), (10, 10), (10, 11), (10, 14), (10, 15)}:
            image.putpixel((x, y), 0)
        row_map = {
            "columns": [{
                "column": 0,
                "left": 0,
                "right": 20,
                "rows": [
                    {"index": 0, "page_top": 0, "page_bottom": 8},
                    {"index": 1, "page_top": 14, "page_bottom": 20},
                ],
            }]
        }

        correction = find_blank_row_boundary(image, row_map, 0, 0, max_shift=4)

        self.assertIsNotNone(correction)
        self.assertEqual((correction["blank_row_top"], correction["blank_row_bottom"]), (8, 9))
        self.assertEqual(correction["corrected_boundary"], 9)
        # Thus the isolated ink at y=10..11 is on the lower side of the cut.
        self.assertLess(correction["corrected_boundary"], 10 + 1)

    def test_no_blank_row_means_no_conclusion(self) -> None:
        image = Image.new("L", (20, 16), 255)
        for y in range(4, 13):
            image.putpixel((2, y), 0)

        correction = find_blank_row_boundary(image, self._row_map(boundary=8), 0, 0, max_shift=4)
        self.assertIsNone(correction)

    def test_blank_tail_without_nearby_ink_below_is_not_a_boundary(self) -> None:
        image = Image.new("L", (20, 16), 255)
        for x, y in {(2, 5), (2, 6), (2, 7)}:
            image.putpixel((x, y), 0)

        correction = find_blank_row_boundary(image, self._row_map(boundary=8), 0, 0, max_shift=4)
        self.assertIsNone(correction)


if __name__ == "__main__":
    unittest.main()
