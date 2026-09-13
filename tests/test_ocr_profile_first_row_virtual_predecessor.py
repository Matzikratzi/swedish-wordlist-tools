from __future__ import annotations

import unittest

from PIL import Image

from swedish_wordlist_tools.ocr_profile_automaton_batch import (
    _column_bounds_with_virtual_first_row_predecessor,
)


class ProfileFirstRowVirtualPredecessorTest(unittest.TestCase):
    def _context(
        self,
        profile_rows: dict[int, int],
        *,
        column_count: int = 1,
    ) -> dict:
        image = Image.new("L", (40, 60), 255)
        px = image.load()

        columns = []
        for column in range(column_count):
            x0 = 5 + column * 15
            px[x0 + 2, 40] = 0
            columns.append(
                {
                    "crop_left": x0,
                    "crop_right": x0 + 10,
                    "crop_top": 0,
                    "rows": [
                        {"page_top": 40, "page_bottom": 45},
                        {"page_top": 48, "page_bottom": 54},
                    ],
                }
            )

        for y, x in profile_rows.items():
            px[x, y] = 0

        return {
            "gray": image,
            "threshold": 210,
            "column_content_lefts": {i: None for i in range(column_count)},
            "row_map": {"columns": columns},
        }

    def test_long_fixed_left_profile_in_column_zero_is_slab(self) -> None:
        profile = {y: 5 for y in range(10, 32)}
        profile[32] = 8
        context = self._context(profile)
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=10,
            min_slab_height=20,
        )
        self.assertEqual(bounds, (5, 15, 32, 54))

    def test_exactly_twenty_rows_is_not_enough(self) -> None:
        profile = {y: 5 for y in range(10, 30)}
        profile[30] = 8
        context = self._context(profile)
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=10,
            min_slab_height=20,
        )
        self.assertEqual(bounds, (5, 15, 10, 54))

    def test_short_fixed_profile_is_normal_first_row(self) -> None:
        profile = {10: 7, 11: 7, 12: 9}
        context = self._context(profile)
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=10,
            min_slab_height=20,
        )
        self.assertEqual(bounds, (5, 15, 10, 54))

    def test_other_columns_never_apply_slab_rule(self) -> None:
        context = self._context({10: 20, 11: 20, 12: 20}, column_count=2)
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            1,
            header_cutoff_y=10,
            min_slab_height=2,
        )
        self.assertEqual(bounds, (20, 30, 10, 54))

    def test_move_left_means_first_ink_belongs_to_text(self) -> None:
        context = self._context({10: 8, 11: 8, 12: 6})
        bounds = _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=10,
            min_slab_height=1,
        )
        self.assertEqual(bounds, (5, 15, 10, 54))

    def test_helper_does_not_create_or_modify_rows(self) -> None:
        profile = {y: 5 for y in range(10, 32)}
        profile[32] = 8
        context = self._context(profile)
        before = list(context["row_map"]["columns"][0]["rows"])
        _column_bounds_with_virtual_first_row_predecessor(
            context,
            0,
            header_cutoff_y=10,
            min_slab_height=20,
        )
        self.assertEqual(context["row_map"]["columns"][0]["rows"], before)
        self.assertEqual(len(context["row_map"]["columns"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
