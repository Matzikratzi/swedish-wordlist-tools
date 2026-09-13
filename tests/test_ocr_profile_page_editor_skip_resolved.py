from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools.ocr_profile_page_editor import ProfilePageEditor


class ProfileEditorSkipResolvedRegressionTest(unittest.TestCase):
    def _editor(self) -> ProfilePageEditor:
        editor = ProfilePageEditor.__new__(ProfilePageEditor)
        editor.jsonl = Path("/tmp/fake.jsonl")
        editor.facit = Path("/tmp/fake-facit.json")
        editor.page_number = 10
        editor.threshold = 210
        editor.prefix_len = 5
        editor.frontier_slack = 5
        editor.regression = Path("/tmp/fake-regression.jsonl")
        editor.regression_targets = [
            (10, 0, 100),
            (11, 0, 110),
            (12, 1, 120),
        ]
        editor.result = {
            "columns": [
                {
                    "column": 0,
                    "deferred_pixels": [[1, 10]],
                    "rows": [
                        {"page_top": 9, "page_bottom": 12, "baseline": 100},
                    ],
                }
            ]
        }
        return editor

    def test_targets_from_page_result_only_includes_rows_with_deferred_pixels(self) -> None:
        result = {
            "columns": [
                {
                    "column": 0,
                    "deferred_pixels": [[3, 15]],
                    "rows": [
                        {"page_top": 10, "page_bottom": 14, "baseline": 101},
                        {"page_top": 14, "page_bottom": 18, "baseline": 102},
                    ],
                },
                {
                    "column": 1,
                    "deferred_pixels": [],
                    "rows": [
                        {"page_top": 20, "page_bottom": 24, "baseline": 201},
                    ],
                },
            ]
        }
        self.assertEqual(
            ProfilePageEditor._targets_from_page_result(7, result),
            [(7, 0, 102)],
        )

    def test_next_navigation_skips_page_that_is_now_clean(self) -> None:
        editor = self._editor()

        def validate(page: int) -> None:
            if page == 11:
                editor._replace_page_targets(11, [])
            elif page == 12:
                editor._replace_page_targets(12, [(12, 1, 121)])

        with patch.object(editor, "_validate_regression_page", side_effect=validate):
            self.assertEqual(
                editor.global_incomplete_nav((10, 0, 100), +1),
                (12, 1, 121),
            )

    def test_previous_navigation_skips_page_that_is_now_clean(self) -> None:
        editor = self._editor()
        editor.regression_targets = [
            (8, 0, 80),
            (9, 2, 90),
            (10, 0, 100),
        ]

        def validate(page: int) -> None:
            if page == 9:
                editor._replace_page_targets(9, [])
            elif page == 8:
                editor._replace_page_targets(8, [(8, 0, 81)])

        with patch.object(editor, "_validate_regression_page", side_effect=validate):
            self.assertEqual(
                editor.global_incomplete_nav((10, 0, 100), -1),
                (8, 0, 81),
            )


if __name__ == "__main__":
    unittest.main()
