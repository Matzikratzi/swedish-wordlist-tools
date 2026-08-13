from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_sequence_ids import analyze


class AnalyzeSaolSequenceIdsTests(unittest.TestCase):
    def test_homonr_zero_can_anchor_to_homonr_two(self) -> None:
        rows = [
            {"normaliserat_ord": "amarant", "homonr": "1", "urspr_lopnr": 440789, "subnr": 440789, "ord": "1amarant"},
            {"normaliserat_ord": "amarant", "homonr": "2", "urspr_lopnr": 440792, "subnr": 440792, "ord": "2amarant"},
            {"normaliserat_ord": "amarant", "homonr": "0", "urspr_lopnr": 440792, "subnr": 440792, "ord": "Amarant"},
        ]
        report = analyze(rows)
        self.assertEqual(1, report["homonr_zero_count"])
        self.assertEqual(1, report["homonr_zero_anchor_counts"]["2"])
        self.assertEqual(1, report["homonr_pattern_counts"]["2,0"])
        self.assertEqual(2, report["article_id_groups"])

    def test_reports_raw_and_distinct_group_jumps_separately(self) -> None:
        rows = [
            {"normaliserat_ord": "a", "homonr": "1", "urspr_lopnr": 100, "subnr": 100},
            {"normaliserat_ord": "a", "homonr": "0", "urspr_lopnr": 100, "subnr": 100},
            {"normaliserat_ord": "b", "homonr": "1", "urspr_lopnr": 103, "subnr": 103},
            {"normaliserat_ord": "c", "homonr": "1", "urspr_lopnr": 104, "subnr": 104},
        ]
        report = analyze(rows)
        self.assertEqual(1, report["raw_urspr_delta_counts"]["0"])
        self.assertEqual(1, report["raw_urspr_delta_counts"]["3"])
        self.assertEqual(1, report["raw_urspr_delta_counts"]["1"])
        self.assertNotIn("0", report["distinct_group_urspr_delta_counts"])
        self.assertEqual(1, report["distinct_group_urspr_delta_counts"]["3"])
        self.assertEqual(1, report["distinct_group_urspr_delta_counts"]["1"])

    def test_counts_urspr_and_subnr_differences(self) -> None:
        rows = [
            {"homonr": "1", "urspr_lopnr": 10, "subnr": 10},
            {"homonr": "1", "urspr_lopnr": 11, "subnr": 12},
        ]
        report = analyze(rows)
        self.assertEqual(1, report["urspr_equals_subnr_rows"])
        self.assertEqual(1, report["urspr_differs_from_subnr_rows"])


if __name__ == "__main__":
    unittest.main()
