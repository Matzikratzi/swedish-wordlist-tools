from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools import ocr_exact_glyph_review_queue_v11 as v11


class DetachedPartGuardTests(unittest.TestCase):
    def test_near_detached_mark_blocks_known_body_only_match(self) -> None:
        body = [[1, 5], [2, 5], [1, 6], [2, 6]]
        accent = [[1, 2], [2, 2]]
        row = {
            "ink": body + accent,
            "uncertain_row": accent,
            "exact": [
                {
                    "label": "a",
                    "style": "bold",
                    "x": 1,
                    "baseline": 6,
                    "pixels": body,
                }
            ],
            "recognized": "a",
            "unexplained": accent,
            "fully_exact": False,
            "baseline_source": "synthetic",
        }

        with patch.object(v11.v10, "_analyse_one", return_value=row):
            got = v11._analyse_one(Path("synthetic.json"), [])

        self.assertEqual(got["exact"], [])
        self.assertEqual(got["recognized"], "")
        self.assertFalse(got["fully_exact"])
        self.assertEqual(
            {tuple(p) for p in got["unexplained"]},
            {tuple(p) for p in body + accent},
        )
        self.assertEqual(len(got["guarded_partial_matches"]), 1)
        self.assertEqual(got["guarded_partial_matches"][0]["label"], "a")
        self.assertEqual(got["guarded_partial_matches"][0]["blocked_by_pixels"], 2)
        self.assertIn("+guard-detached(1)", got["baseline_source"])

    def test_complete_accented_model_is_not_blocked(self) -> None:
        body = [[1, 5], [2, 5], [1, 6], [2, 6]]
        accent = [[1, 2], [2, 2]]
        whole = body + accent
        row = {
            "ink": whole,
            "uncertain_row": accent,
            "exact": [
                {
                    "label": "á",
                    "style": "bold",
                    "x": 1,
                    "baseline": 6,
                    "pixels": whole,
                }
            ],
            "recognized": "á",
            "unexplained": [],
            "fully_exact": True,
            "baseline_source": "synthetic",
        }

        with patch.object(v11.v10, "_analyse_one", return_value=row):
            got = v11._analyse_one(Path("synthetic.json"), [])

        self.assertEqual(len(got["exact"]), 1)
        self.assertEqual(got["recognized"], "á")
        self.assertTrue(got["fully_exact"])
        self.assertEqual(got["unexplained"], [])
        self.assertEqual(got["guarded_partial_matches"], [])
        self.assertEqual(got["baseline_source"], "synthetic")

    def test_lower_neighbor_row_is_never_reintroduced_as_unexplained(self) -> None:
        body = [[1, 5], [2, 5], [1, 6], [2, 6]]
        accent = [[1, 2], [2, 2]]
        lower_row = [[1, 11], [2, 11], [1, 12], [2, 12]]
        row = {
            "ink": body + accent + lower_row,
            "uncertain_row": accent,
            "previous_row": [],
            "next_row": lower_row,
            "exact": [
                {
                    "label": "a",
                    "style": "bold",
                    "x": 1,
                    "baseline": 6,
                    "pixels": body,
                }
            ],
            "recognized": "a",
            "unexplained": accent,
            "fully_exact": False,
            "baseline_source": "synthetic",
        }

        with patch.object(v11.v10, "_analyse_one", return_value=row):
            got = v11._analyse_one(Path("synthetic.json"), [])

        self.assertEqual(got["exact"], [])
        self.assertEqual(
            {tuple(p) for p in got["unexplained"]},
            {tuple(p) for p in body + accent},
        )
        self.assertTrue({tuple(p) for p in got["unexplained"]}.isdisjoint({tuple(p) for p in lower_row}))


if __name__ == "__main__":
    unittest.main()
