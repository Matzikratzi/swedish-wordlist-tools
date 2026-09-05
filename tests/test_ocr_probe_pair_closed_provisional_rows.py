from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_pair_closed_provisional_rows import PairClosureResult


class PairClosureResultTests(unittest.TestCase):
    def test_result_records_pixel_proven_commit_state(self):
        result = PairClosureResult(
            upper=(0, 1), lower=(0, 2), proposed_pixels=4, committed_pixels=4,
            upper_before_exact=False, upper_after_exact=True, lower_after_exact=False,
            transferred_pixels_explained=4, transferred_pixels_total=4,
            committed=True,
            upper_before_covered=10, upper_before_source=14,
            upper_after_covered=10, upper_after_source=10,
            lower_after_covered=20, lower_after_source=25,
            upper_before_seconds=1.0, upper_after_seconds=0.1, lower_after_seconds=0.1,
            secure_bottom_page_y=100,
        )
        self.assertTrue(result.committed)
        self.assertEqual(result.proposed_pixels, result.committed_pixels)
        self.assertFalse(result.lower_after_exact)
        self.assertEqual(result.transferred_pixels_explained, result.transferred_pixels_total)


if __name__ == "__main__":
    unittest.main()
