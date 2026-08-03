from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_rule_usage import build_report, classify_rule_path


class AnalyzeRuleUsageTests(unittest.TestCase):
    def record(self, lemma: str, pattern: str, upos: str = "NOUN", stycke: str = ""):
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "upos": upos,
            "stycke": stycke,
        }

    def test_classifies_common_and_completion_paths(self) -> None:
        self.assertEqual(
            "noun_completion_after_base_generation",
            classify_rule_path(self.record("hund", "+en +ar")),
        )
        self.assertEqual(
            "noun_completion_from_unsupported",
            classify_rule_path(self.record("parti", "+et +er")),
        )

    def test_classifies_bar_marked_short_plural(self) -> None:
        self.assertEqual(
            "noun_completion_after_base_generation",
            classify_rule_path(
                self.record("alarmklocka", "+n -klockor", stycke="a·larm|klocka")
            ),
        )

    def test_reports_unused_common_patterns(self) -> None:
        report = build_report([self.record("hund", "+en +ar")])
        self.assertEqual(1, report["records"])
        self.assertEqual(1, report["common_pattern_counts"]["+en +ar"])
        self.assertIn("+de +t", report["unused_common_patterns"])


if __name__ == "__main__":
    unittest.main()
