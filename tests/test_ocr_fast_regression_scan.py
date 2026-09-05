from __future__ import annotations

import unittest
from unittest.mock import patch

from PIL import Image

from swedish_wordlist_tools.ocr_fast_regression_scan import analyse_row_fast_only


class FastRegressionAnalyserTests(unittest.TestCase):
    def test_fast_miss_never_uses_exhaustive_fallback(self):
        crop = Image.new("L", (3, 3), 255)
        crop.putpixel((1, 1), 0)
        with patch(
            "swedish_wordlist_tools.ocr_fast_regression_scan.page_cached_prioritized_fast_exact_cover",
            return_value=None,
        ) as fast:
            result = analyse_row_fast_only(crop, [], threshold=210)
        fast.assert_called_once()
        self.assertFalse(result["fully_exact"])
        self.assertEqual(result["source_pixels"], 1)
        self.assertEqual(result["covered_pixels"], 0)
        self.assertEqual(result["exact_cover_path"], "fast-regression-miss")

    def test_empty_crop_is_exact_without_search(self):
        crop = Image.new("L", (3, 3), 255)
        with patch(
            "swedish_wordlist_tools.ocr_fast_regression_scan.page_cached_prioritized_fast_exact_cover"
        ) as fast:
            result = analyse_row_fast_only(crop, [], threshold=210)
        fast.assert_not_called()
        self.assertTrue(result["fully_exact"])
        self.assertEqual(result["source_pixels"], 0)


if __name__ == "__main__":
    unittest.main()
