from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_profile_automaton_batch import (
    _column_bounds_with_virtual_first_row_predecessor,
)


class ProfileFirstRowVirtualPredecessorTest(unittest.TestCase):
    def _context(self, *, extra_ink_y: int | None) -> dict:
        image = Image.new("L", (20, 20), 255)
        px = image.load()
        # Ink belonging to the segmented first row.
        px[7, 8] = 0
        if extra_ink_y is not None:
            px[9, extra_ink_y] = 0
        return {
            "gray": image,
            "threshold": 210,
            "column_content_lefts": {0: None},
            "row_map": {
                "columns": [
                    {
                        "crop_left": 5,
                        "crop_right": 15,
                        "crop_top": 2,
                        "rows": [
                            {"page_top": 8, "page_bottom": 12},
                            {"page_top": 14, "page_bottom": 18},
                        ],
                    }
                ]
            },
        }

    def test_first_row_top_expands_to_highest_column_ink(self) -> None:
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            self._context(extra_ink_y=5),
            0,
        )
        self.assertEqual(bounds, (5, 15, 5, 18))

    def test_no_extra_ink_keeps_segmented_first_row_top(self) -> None:
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            self._context(extra_ink_y=None),
            0,
        )
        self.assertEqual(bounds, (5, 15, 8, 18))

    def test_helper_does_not_create_or_modify_rows(self) -> None:
        context = self._context(extra_ink_y=5)
        before = list(context["row_map"]["columns"][0]["rows"])
        _column_bounds_with_virtual_first_row_predecessor(context, 0)
        self.assertEqual(context["row_map"]["columns"][0]["rows"], before)
        self.assertEqual(len(context["row_map"]["columns"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
