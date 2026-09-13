from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_profile_automaton_batch import (
    _column_bounds_with_virtual_first_row_predecessor,
)


class ProfileFirstRowVirtualPredecessorTest(unittest.TestCase):
    def _context(self, upper_ink_rows: tuple[int, ...] = ()) -> dict:
        image = Image.new("L", (20, 20), 255)
        px = image.load()
        px[7, 8] = 0
        for y in upper_ink_rows:
            px[9, y] = 0
        return {
            "gray": image,
            "threshold": 210,
            "column_content_lefts": {0: None},
            "row_map": {
                "columns": [
                    {
                        "crop_left": 5,
                        "crop_right": 15,
                        "crop_top": 0,
                        "rows": [
                            {"page_top": 8, "page_bottom": 12},
                            {"page_top": 14, "page_bottom": 18},
                        ],
                    }
                ]
            },
        }

    def test_ignores_header_ink_above_cutoff(self) -> None:
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            self._context((3, 6)),
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 6, 18))

    def test_uses_highest_ink_at_or_below_cutoff(self) -> None:
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            self._context((5, 7)),
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 5, 18))

    def test_no_ink_between_cutoff_and_segmented_top_keeps_original_top(self) -> None:
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            self._context((3,)),
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 8, 18))

    def test_helper_does_not_create_or_modify_rows(self) -> None:
        context = self._context((6,))
        before = list(context["row_map"]["columns"][0]["rows"])
        _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(context["row_map"]["columns"][0]["rows"], before)
        self.assertEqual(len(context["row_map"]["columns"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
