from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_review_five_rows_glyphs_boundary_html import _gap_boundaries_around_row


class BoundaryGapTriggerTests(unittest.TestCase):
    def test_gap_above_target_is_considered_even_without_edge_residual(self) -> None:
        rows = [
            {"page_top": 0, "page_bottom": 17},
            {"page_top": 23, "page_bottom": 35},
            {"page_top": 37, "page_bottom": 53},
        ]
        self.assertEqual(_gap_boundaries_around_row(rows, 1), [0, 1])

    def test_shared_boundaries_need_no_pre_review_normalization(self) -> None:
        rows = [
            {"page_top": 0, "page_bottom": 17},
            {"page_top": 17, "page_bottom": 35},
            {"page_top": 35, "page_bottom": 53},
        ]
        self.assertEqual(_gap_boundaries_around_row(rows, 1), [])


if __name__ == "__main__":
    unittest.main()
