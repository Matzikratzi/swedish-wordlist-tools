from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_probe_provisional_row_boundary import provisional_lower_pixels


class ProvisionalRowBoundaryTests(unittest.TestCase):
    def test_only_unmatched_pixels_at_or_below_deepest_match_move(self):
        match = Match(
            label="a",
            style="roman",
            x=0,
            baseline=5,
            pixels=frozenset({(0, 0), (1, 1), (1, 2)}),
            model_pixels=3,
            sources=1,
        )
        state = {
            "crop_box": (10, 20, 30, 40),
            "matches": [match],
            "source_ink_points": [
                [0, 0], [1, 1], [1, 2],
                [4, 1],          # unmatched but above secure bottom: stays upper
                [5, 3], [6, 4],  # unmatched at/below secure bottom: provisional lower
            ],
        }
        secure_bottom, pixels = provisional_lower_pixels(state)
        self.assertEqual(secure_bottom, 23)
        self.assertEqual(pixels, {(15, 23), (16, 24)})

    def test_no_matches_means_no_provisional_move(self):
        state = {
            "crop_box": (0, 0, 20, 20),
            "matches": [],
            "source_ink_points": [[1, 1], [2, 2]],
        }
        secure_bottom, pixels = provisional_lower_pixels(state)
        self.assertIsNone(secure_bottom)
        self.assertEqual(pixels, set())


if __name__ == "__main__":
    unittest.main()
