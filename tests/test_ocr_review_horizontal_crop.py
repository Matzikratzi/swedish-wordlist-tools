from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_unique_unknown_glyph_review import (
    _cropped_review_context,
    _review_x_bounds,
)


class HorizontalReviewCropTests(unittest.TestCase):
    def test_crop_stops_at_two_consecutive_blank_columns(self) -> None:
        # Candidate at x=10..11. There is only one blank column at x=9 before
        # another target-row glyph at x=7..8, so review must continue left past
        # that glyph until the genuinely blank run x=5..6 is reached.
        ink = [
            [7, 5], [8, 5],
            [10, 5], [11, 5],
            [14, 5],
        ]
        group = {(10, 5), (11, 5)}

        self.assertEqual(_review_x_bounds(ink, group, 20), (5, 13))

    def test_context_rebases_pixels_and_keeps_two_blank_columns(self) -> None:
        row = {
            "width": 20,
            "height": 12,
            "ink": [
                [7, 5], [8, 5],
                [10, 5], [11, 5],
                [14, 5],
            ],
            "exact": [
                {
                    "label": "x",
                    "style": "unknown",
                    "x": 7,
                    "baseline": 6,
                    "pixels": [[7, 5], [8, 5]],
                }
            ],
            "jsonl_hint": {"text": "+de"},
        }
        group = {(10, 5), (11, 5)}

        context = _cropped_review_context(row, group, 6)

        self.assertEqual(context["review_x_offset"], 5)
        self.assertEqual(context["width"], 9)
        self.assertEqual(context["review_free_columns_x"], 2)
        self.assertEqual(context["candidate_pixels"], [[5, 1], [6, 1]])
        self.assertEqual(context["exact"][0]["x"], 2)

        occupied_x = {x for x, _ in context["ink"]}
        self.assertNotIn(0, occupied_x)
        self.assertNotIn(1, occupied_x)
        self.assertNotIn(context["width"] - 1, occupied_x)


if __name__ == "__main__":
    unittest.main()
