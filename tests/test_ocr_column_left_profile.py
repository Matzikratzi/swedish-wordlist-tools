from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_column_left_profile import build_column_left_profile


class ColumnLeftProfileTests(unittest.TestCase):
    def test_builds_absolute_leftmost_profile_once(self) -> None:
        rows = {
            10: {9, 5, 7},
            11: {5, 8},
            13: {6, 12},
        }

        profile = build_column_left_profile(rows, top=10, bottom=15, left=4, right=10)

        self.assertEqual(profile.values, (5, 5, None, 6, None))
        self.assertEqual(profile.at(10), 5)
        self.assertEqual(profile.at(12), None)
        self.assertEqual(profile.row_leftmost(11, 14), 5)

    def test_changes_omit_unchanged_dx_zero_rows(self) -> None:
        rows = {
            20: {7},
            21: {7, 9},
            22: {5},
            24: {5},
        }
        profile = build_column_left_profile(rows, top=20, bottom=25)

        self.assertEqual(
            profile.changes(),
            (
                (22, 7, 5),
                (23, 5, None),
                (24, None, 5),
            ),
        )


if __name__ == "__main__":
    unittest.main()
