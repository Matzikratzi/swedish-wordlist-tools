from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_final_adjudication import (
    adjudicate,
    build_report,
)


class AnalyzeAdjectiveFinalAdjudicationTests(unittest.TestCase):
    def test_adjudication_categories(self) -> None:
        self.assertEqual(
            "confirmed_saldo_gap",
            adjudicate("absent_from_all_saldo", True),
        )
        self.assertEqual(
            "saldo_adjective_alignment",
            adjudicate("found_in_other_saldo_adjective_analysis", False),
        )
        self.assertEqual(
            "saldo_pos_or_adjective_coverage_review",
            adjudicate("only_non_adjective_saldo_match", False),
        )

    def test_build_report_uses_confirmed_absent_cases(self) -> None:
        rows = [{
            "lemma": "allgod",
            "classified_missing_forms": [{
                "slot": "neuter_singular",
                "written_form": "allgott",
                "provenance": "replace_tail",
                "source_token": "-gott",
                "global_saldo_status": "absent_from_all_saldo",
            }],
        }]
        report, cases = build_report(
            rows,
            {("allgod", "neuter_singular", "allgott")},
        )
        self.assertEqual(1, report["cases"])
        self.assertEqual(
            {"confirmed_saldo_gap": 1},
            report["adjudication_counts"],
        )
        self.assertEqual("confirmed_saldo_gap", cases[0]["final_adjudication"])

    def test_alignment_and_pos_cases_are_kept_separate(self) -> None:
        rows = [{
            "lemma": "fasetterad",
            "classified_missing_forms": [
                {
                    "slot": "common_singular",
                    "written_form": "facetterad",
                    "global_saldo_status": "found_in_other_saldo_adjective_analysis",
                },
                {
                    "slot": "definite_or_plural",
                    "written_form": "gjorda",
                    "global_saldo_status": "only_non_adjective_saldo_match",
                },
            ],
        }]
        report, _cases = build_report(rows, set())
        self.assertEqual(
            {
                "saldo_adjective_alignment": 1,
                "saldo_pos_or_adjective_coverage_review": 1,
            },
            report["adjudication_counts"],
        )


if __name__ == "__main__":
    unittest.main()
