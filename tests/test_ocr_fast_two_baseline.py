from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_fast_two_baseline import TwoBaselineExactResult


class TwoBaselineFastPathTests(unittest.TestCase):
    def test_result_records_single_switch(self):
        result = TwoBaselineExactResult(
            baseline=16,
            selected=(),
            placements_tested=7,
            baseline_switches=(
                {"x": 20, "from_baseline": 16, "to_baseline": 15, "delta": -1},
            ),
        )
        self.assertEqual(result.baseline, 16)
        self.assertEqual(result.placements_tested, 7)
        self.assertEqual(len(result.baseline_switches), 1)
        self.assertEqual(result.baseline_switches[0]["delta"], -1)


if __name__ == "__main__":
    unittest.main()
