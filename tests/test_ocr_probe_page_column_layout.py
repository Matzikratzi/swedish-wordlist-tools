from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_page_column_layout import (
    longest_low_run,
    parity_summary,
    parse_pages,
    stable_mode,
)


class TestOcrProbePageColumnLayout(unittest.TestCase):
    def test_parse_pages(self):
        self.assertEqual(parse_pages("1-3,5,3"), [1, 2, 3, 5])

    def test_stable_mode_ignores_homonym_outliers(self):
        self.assertEqual(stable_mode([12, 12, 12, 13, 12, 8, 8]), 12)

    def test_longest_low_run_accepts_one_pixel_scanner_noise(self):
        counts = {10: 7, 11: 1, 12: 0, 13: 1, 14: 0, 15: 8, 16: 0}
        self.assertEqual(longest_low_run(counts), (11, 15, 0))

    def test_parity_summary_keeps_even_and_odd_separate(self):
        records = [
            {"page": 1, "column_starts": [10, 110, 210], "boundaries": [95, 195]},
            {"page": 3, "column_starts": [11, 111, 211], "boundaries": [96, 196]},
            {"page": 2, "column_starts": [12, 112, 212], "boundaries": [97, 197]},
            {"page": 4, "column_starts": [12, 112, 212], "boundaries": [97, 197]},
        ]
        lines = parity_summary(records)
        self.assertIn("jämna: column_starts=[12 (12..12), 112 (112..112), 212 (212..212)]", lines)
        self.assertIn("udda: boundaries=[96 (95..96), 196 (195..196)]", lines)


if __name__ == "__main__":
    unittest.main()
