from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_saldo_absent_review import (
    build_report,
    review_priority,
)


class AnalyzeAdjectiveSaldoAbsentReviewTests(unittest.TestCase):
    def test_prioritizes_explicit_before_generated_forms(self) -> None:
        self.assertLess(
            review_priority({"provenance": "explicit", "source_token": "durabla"})[0],
            review_priority({"provenance": "append", "source_token": "+a"})[0],
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
        self.assertEqual("regular_append_form", cases[0]["review_group"])


if __name__ == "__main__":
    unittest.main()
