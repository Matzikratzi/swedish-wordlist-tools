from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_saldo_absent_review import (
    build_report,
    review_assessment,
    review_priority,
)


class AnalyzeAdjectiveSaldoAbsentReviewTests(unittest.TestCase):
    def test_prioritizes_explicit_before_generated_forms(self) -> None:
        self.assertLess(
            review_priority({"provenance": "explicit", "source_token": "durabla"})[0],
            review_priority({"provenance": "append", "source_token": "+a"})[0],
        )

    def test_assesses_explicit_as_strong_saldo_gap_candidate(self) -> None:
        self.assertEqual(
            "strong_saldo_gap_candidate",
            review_assessment({"provenance": "explicit", "source_token": "durabla"}),
        )

    def test_assesses_regular_append_separately_from_replace_tail(self) -> None:
        self.assertEqual(
            "standard_notation_saldo_gap_candidate",
            review_assessment({"provenance": "append", "source_token": "+a"}),
        )
        self.assertEqual(
            "targeted_saol_notation_review",
            review_assessment({"provenance": "replace_tail", "source_token": "-gott"}),
        )
        self.assertEqual(
            "strong_saldo_gap_candidate",
            review_assessment(
                {"provenance": "replace_tail", "source_token": "-gott"},
                replace_tail_confirmed=True,
            ),
        )

    def test_build_report_only_includes_forms_absent_from_all_saldo(self) -> None:
        report, cases = build_report([
            {
                "lemma": "durabel",
                "classified_missing_forms": [
                    {
                        "written_form": "durabla",
                        "slot": "definite_or_plural",
                        "provenance": "explicit",
                        "source_token": "durabla",
                        "operation_base": "durabla",
                        "global_saldo_status": "absent_from_all_saldo",
                    },
                    {
                        "written_form": "durabelt",
                        "slot": "neuter_singular",
                        "provenance": "append",
                        "source_token": "+t",
                        "operation_base": "durabel",
                        "global_saldo_status": "found_in_other_saldo_adjective_analysis",
                    },
                ],
            }
        ])
        self.assertEqual(1, report["cases"])
        self.assertEqual("durabla", cases[0]["written_form"])
        self.assertEqual("explicit_saol_form", cases[0]["review_group"])
        self.assertEqual(
            "strong_saldo_gap_candidate",
            cases[0]["review_assessment"],
        )

    def test_bar_confirmed_replace_tail_is_promoted(self) -> None:
        rows = [{
            "lemma": "allgod",
            "classified_missing_forms": [{
                "written_form": "allgott",
                "slot": "neuter_singular",
                "provenance": "replace_tail",
                "source_token": "-gott",
                "operation_base": "allgod",
                "global_saldo_status": "absent_from_all_saldo",
            }],
        }]
        report, cases = build_report(
            rows,
            {("allgod", "neuter_singular", "allgott")},
        )
        self.assertEqual(1, report["confirmed_replace_tail_cases"])
        self.assertTrue(cases[0]["bar_notation_confirmed"])
        self.assertEqual(
            "strong_saldo_gap_candidate",
            cases[0]["review_assessment"],
        )

    def test_regular_append_is_grouped_last(self) -> None:
        report, cases = build_report([
            {
                "lemma": "bakåtböjd",
                "classified_missing_forms": [{
                    "written_form": "bakåtböjda",
                    "slot": "definite_or_plural",
                    "provenance": "append",
                    "source_token": "+a",
                    "operation_base": "bakåtböjd",
                    "global_saldo_status": "absent_from_all_saldo",
                }],
            }
        ])
        self.assertEqual({"regular_append_form": 1}, report["review_group_counts"])
        self.assertEqual(
            {"standard_notation_saldo_gap_candidate": 1},
            report["review_assessment_counts"],
        )
        self.assertEqual("regular_append_form", cases[0]["review_group"])


if __name__ == "__main__":
    unittest.main()
