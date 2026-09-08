from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_row_split_left_support import split_left_support_decision


class RowSplitLeftSupportTests(unittest.TestCase):
    def test_late_tiny_fragment_is_not_allowed_to_establish_own_row(self) -> None:
        # Apne-like geometry: the following real row starts around x=57 while
        # the tiny upper fragment is almost 30 px into the row.
        upper = {(85, 0), (85, 1), (86, 1), (87, 1), (86, 2)}
        lower = {
            (57, 4), (58, 4), (59, 4),
            (57, 5), (58, 5), (60, 5),
            (57, 6), (59, 6), (61, 6),
            (58, 7), (60, 7), (62, 7),
        }

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(28, decision.start_delta)
        self.assertFalse(decision.upper_has_own_left_support)
        self.assertTrue(decision.looks_like_late_upper_fragment)

    def test_low_continuation_row_with_own_left_support_is_preserved(self) -> None:
        # A deliberately low continuation row: only four raster rows high, but
        # it starts at the left margin and has real multi-row glyph structure.
        upper = {
            (58, 0), (59, 0), (60, 0),
            (58, 1), (60, 1), (61, 1),
            (58, 2), (59, 2), (61, 2),
            (59, 3), (60, 3), (61, 3),
        }
        lower = {
            (57, 8), (58, 8), (59, 8),
            (57, 9), (60, 9),
            (57, 10), (59, 10), (61, 10),
            (58, 11), (60, 11),
        }

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(1, decision.start_delta)
        self.assertTrue(decision.upper_has_own_left_support)
        self.assertFalse(decision.looks_like_late_upper_fragment)

    def test_indented_but_real_continuation_row_is_preserved(self) -> None:
        upper = {
            (68, 0), (69, 0), (70, 0),
            (68, 1), (70, 1),
            (68, 2), (69, 2), (71, 2),
            (69, 3), (70, 3),
        }
        lower = {(57, y) for y in range(8, 13)} | {(58, y) for y in range(8, 13)}

        decision = split_left_support_decision(upper, lower)

        self.assertEqual(11, decision.start_delta)
        self.assertTrue(decision.upper_has_own_left_support)
        self.assertFalse(decision.looks_like_late_upper_fragment)


if __name__ == "__main__":
    unittest.main()
