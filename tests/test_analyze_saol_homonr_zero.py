from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_homonr_zero import classify


class AnalyzeSaolHomonrZeroTests(unittest.TestCase):
    def test_zero_after_homonr_two_is_article_variant(self) -> None:
        rows = [
            {"normaliserat_ord": "amarant", "homonr": "2", "urspr_lopnr": 440792, "subnr": 440792, "ord": "amarant", "ordkl": "s.", "text": "+en"},
            {"normaliserat_ord": "amarant", "homonr": "0", "urspr_lopnr": 440792, "subnr": 440792, "ord": "Amarant", "ordkl": "s.", "text": "+en"},
        ]
        output, summary = classify(rows)
        self.assertEqual("article_variant", output[0]["classification"])
        self.assertEqual(["2"], output[0]["anchor_homonr"])
        self.assertEqual(1, summary["classification_counts"]["article_variant"])

    def test_standalone_hv_zero_is_reference_entry(self) -> None:
        rows = [
            {"normaliserat_ord": "den", "homonr": "0", "urspr_lopnr": 424558, "subnr": 424558, "ord": "de", "ordkl": "(hv)", "text": "(null)", "upos": "X"},
        ]
        output, summary = classify(rows)
        self.assertEqual("reference_entry", output[0]["classification"])
        self.assertEqual([], output[0]["anchor_homonr"])
        self.assertEqual(1, summary["classification_counts"]["reference_entry"])

    def test_multiple_reference_rows_to_same_normalized_target_are_counted(self) -> None:
        rows = [
            {"normaliserat_ord": "den", "homonr": "0", "urspr_lopnr": 424558, "subnr": 424558, "ord": "de", "ordkl": "(hv)", "text": "(null)", "upos": "X"},
            {"normaliserat_ord": "den", "homonr": "0", "urspr_lopnr": 424561, "subnr": 424561, "ord": "de", "ordkl": "(hv)", "text": "(null)", "upos": "X"},
            {"normaliserat_ord": "den", "homonr": "0", "urspr_lopnr": 425712, "subnr": 425712, "ord": "dem", "ordkl": "(hv)", "text": "(null)", "upos": "X"},
        ]
        _, summary = classify(rows)
        self.assertEqual(1, summary["reference_targets_with_multiple_rows"])
        self.assertEqual({"normaliserat_ord": "den", "rows": 3}, summary["top_reference_targets"][0])


if __name__ == "__main__":
    unittest.main()
