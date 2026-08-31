from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_white_gap_text import grouped_row_text


class WhiteGapTextProbeTests(unittest.TestCase):
    def test_groups_words_by_row_and_sorts_left_to_right(self) -> None:
        records = [
            {
                "column": 0,
                "row_index": 1,
                "row_page_top": 20,
                "row_page_bottom": 35,
                "row_source": "white-gap-single",
                "text": "s.",
                "bbox": [40, 20, 5, 10],
            },
            {
                "column": 0,
                "row_index": 1,
                "row_page_top": 20,
                "row_page_bottom": 35,
                "row_source": "white-gap-single",
                "text": "abborre",
                "bbox": [10, 20, 25, 10],
            },
            {
                "column": 1,
                "row_index": 0,
                "row_page_top": 10,
                "row_page_bottom": 25,
                "row_source": "white-gap-single",
                "text": "annan",
                "bbox": [250, 10, 20, 10],
            },
        ]

        rows = grouped_row_text(records)
        self.assertEqual([(row["column"], row["row_index"]) for row in rows], [(0, 1), (1, 0)])
        self.assertEqual(rows[0]["text"], "abborre s.")
        self.assertEqual(rows[0]["page_top"], 20)
        self.assertEqual(rows[0]["page_bottom"], 35)


if __name__ == "__main__":
    unittest.main()
