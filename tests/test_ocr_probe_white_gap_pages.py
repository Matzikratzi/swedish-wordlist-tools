from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_white_gap_pages import parse_pages


class WhiteGapPagesProbeTests(unittest.TestCase):
    def test_parse_pages_accepts_ranges_and_deduplicates(self) -> None:
        self.assertEqual(parse_pages("1,3,5-7,6,10-9"), [1, 3, 5, 6, 7, 9, 10])

    def test_parse_pages_ignores_non_positive_pages(self) -> None:
        self.assertEqual(parse_pages("0,-1,2"), [1, 2])


if __name__ == "__main__":
    unittest.main()
