from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_profile_leftmost_baseline_seed_benchmark import (
    _reconstruct_rows_from_accepted_streams,
)


def entry(left, right, label, top, bottom):
    return (left, right, 0, left, label, "roman", top, bottom)


class ProfileRowContainmentTests(unittest.TestCase):
    def test_contained_row_merges_even_when_baselines_are_not_adjacent(self):
        streams = {
            925: [
                entry(10, 15, "a", 914, 925),
                entry(20, 26, "n", 915, 925),
                entry(30, 35, "d", 914, 925),
            ],
            921: [
                entry(104, 110, "u", 916, 921),
            ],
        }

        rows = _reconstruct_rows_from_accepted_streams(streams)

        self.assertEqual(len(rows), 1)
        representative, members, top, bottom, text, glyph_count = rows[0]
        self.assertEqual(representative, 925)
        self.assertEqual(set(members), {921, 925})
        self.assertEqual((top, bottom), (914, 925))
        self.assertEqual(glyph_count, 4)
        self.assertEqual(text, "andu")

    def test_partial_vertical_overlap_does_not_merge_rows(self):
        streams = {
            925: [
                entry(10, 15, "a", 914, 925),
                entry(20, 26, "n", 915, 925),
            ],
            931: [
                entry(104, 110, "u", 920, 931),
            ],
        }

        rows = _reconstruct_rows_from_accepted_streams(streams)

        self.assertEqual(len(rows), 2)
        self.assertEqual({row[0] for row in rows}, {925, 931})


if __name__ == "__main__":
    unittest.main()
