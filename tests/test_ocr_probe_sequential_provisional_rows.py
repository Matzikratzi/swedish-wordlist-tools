from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_probe_sequential_provisional_rows import SequentialRowResult


class SequentialProvisionalRowsTest(unittest.TestCase):
    def test_result_tracks_handed_down_pixels(self):
        result = SequentialRowResult(
            position=(1, 7),
            incoming_pixels=5,
            moved_pixels=3,
            secure_bottom_page_y=123,
            before_exact=False,
            after_exact=True,
            before_source_pixels=20,
            before_covered_pixels=17,
            after_source_pixels=17,
            after_covered_pixels=17,
            before_seconds=1.0,
            after_seconds=0.01,
        )
        self.assertEqual(result.incoming_pixels, 5)
        self.assertEqual(result.moved_pixels, 3)
        self.assertFalse(result.before_exact)
        self.assertTrue(result.after_exact)


if __name__ == "__main__":
    unittest.main()
