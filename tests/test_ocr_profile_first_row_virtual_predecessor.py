from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_profile_automaton_batch import (
    _column_bounds_with_virtual_first_row_predecessor,
)


class ProfileFirstRowVirtualPredecessorTest(unittest.TestCase):
    def _context(self, profile_rows: dict[int, int]) -> dict:
        image = Image.new("L", (20, 20), 255)
        px = image.load()
        # First segmented text row begins at y=8.
        px[7, 8] = 0
        for y, x in profile_rows.items():
            px[x, y] = 0
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

    def test_fixed_left_slab_ends_when_profile_moves_right(self) -> None:
        context = self._context({5: 5, 6: 5, 7: 9})
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 7, 18))

    def test_blank_rows_inside_slab_do_not_end_it(self) -> None:
        context = self._context({5: 5, 7: 5})
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 8, 18))

    def test_profile_moving_left_is_not_treated_as_slab_end(self) -> None:
        context = self._context({5: 7, 6: 6})
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 8, 18))

    def test_no_ink_below_cutoff_keeps_segmented_top(self) -> None:
        context = self._context({})
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=5,
        )
        self.assertEqual(bounds, (5, 15, 8, 18))

    def test_helper_does_not_create_or_modify_rows(self) -> None:
        context = self._context({5: 5, 6: 5, 7: 9})
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
