from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_replace_tail_review import (
    analyze_case,
    build_report,
)


class AnalyzeAdjectiveReplaceTailReviewTests(unittest.TestCase):
    def test_bar_notation_confirms_replacement(self) -> None:
        case = analyze_case({
            "lemma": "hjärteglad",
            "stycke": "hjärte|glad",
            "slot": "neuter_singular",
            "written_form": "hjärteglatt",
            "provenance": "replace_tail",
            "source_token": "-glatt",
            "operation_base": "hjärteglad",
            "review_group": "replace_tail_form",
        })
        self.assertEqual("hjärte", case["bar_prefix"])
        self.assertEqual("hjärteglatt", case["bar_reconstructed_form"])
        self.assertEqual("bar_notation_confirms_form", case["replace_tail_assessment"])

    def test_report_only_includes_replace_tail_group(self) -> None:
        report, cases = build_report([
            {
                "lemma": "allgod",
                "stycke": "all|god",
                "slot": "neuter_singular",
                "written_form": "allgott",
                "provenance": "replace_tail",
                "source_token": "-gott",
                "operation_base": "allgod",
                "review_group": "replace_tail_form",
            },
            {
                "lemma": "glödröd",
                "stycke": "glöd|röd",
                "slot": "definite_or_plural",
                "written_form": "glödröda",
                "provenance": "append",
                "source_token": "+a",
                "operation_base": "glödröd",
                "review_group": "regular_append_form",
            },
        ])
        self.assertEqual(1, report["cases"])
        self.assertEqual(1, len(cases))
        self.assertEqual({"bar_notation_confirms_form": 1}, report["assessment_counts"])


if __name__ == "__main__":
    unittest.main()
