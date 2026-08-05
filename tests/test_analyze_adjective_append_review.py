from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_append_review import (
    analyze_case,
    build_report,
)


class AnalyzeAdjectiveAppendReviewTests(unittest.TestCase):
    def test_literal_plus_a_confirms_form(self) -> None:
        result = analyze_case({
            "lemma": "bakåtböjd",
            "written_form": "bakåtböjda",
            "slot": "definite_or_plural",
            "operation_base": "bakåtböjd",
            "source_token": "+a",
        })
        self.assertEqual("literal_append_confirms_form", result["append_assessment"])
        self.assertEqual("bakåtböjda", result["literal_appended_form"])

    def test_literal_plus_t_confirms_form(self) -> None:
        result = analyze_case({
            "lemma": "camp",
            "written_form": "campt",
            "slot": "neuter_singular",
            "operation_base": "camp",
            "source_token": "+t",
        })
        self.assertEqual("literal_append_confirms_form", result["append_assessment"])
        self.assertEqual("campt", result["literal_appended_form"])

    def test_explicit_glatt_is_not_treated_as_plus_t(self) -> None:
        result = analyze_case({
            "lemma": "glad",
            "written_form": "glatt",
            "slot": "neuter_singular",
            "operation_base": "glatt",
            "source_token": "glatt",
        })
        self.assertEqual("needs_manual_append_review", result["append_assessment"])
        self.assertEqual("", result["literal_appended_form"])

    def test_build_report_only_uses_regular_append_group(self) -> None:
        report, cases = build_report([
            {
                "lemma": "bakåtböjd",
                "review_group": "regular_append_form",
                "written_form": "bakåtböjda",
                "slot": "definite_or_plural",
                "operation_base": "bakåtböjd",
                "source_token": "+a",
            },
            {
                "lemma": "allgod",
                "review_group": "replace_tail_form",
                "written_form": "allgott",
                "slot": "neuter_singular",
                "operation_base": "allgod",
                "source_token": "-gott",
            },
        ])
        self.assertEqual(1, report["cases"])
        self.assertEqual(1, len(cases))


if __name__ == "__main__":
    unittest.main()
