from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_mismatch_patterns import analyse_rows


class AnalyzeNounMismatchPatternsTests(unittest.TestCase):
    def test_groups_noun_mismatches_and_reports_remaining_totals(self) -> None:
        rows = [
            {
                "status": "form_set_mismatch",
                "upos": "NOUN",
                "lemma": "chatt",
                "homonym_number": "2",
                "notation": "+et; pl. +",
                "match_method": "lemma_same_upos",
                "extra_from_saol": ["chattet", "chattets"],
                "missing_from_saol": ["chattar", "chattarna"],
            },
            {
                "status": "form_set_mismatch",
                "upos": "NOUN",
                "lemma": "klapp",
                "homonym_number": "2",
                "notation": "+et; pl. +",
                "match_method": "lemma_same_upos",
                "extra_from_saol": ["klappet", "klappets"],
                "missing_from_saol": ["klappar", "klapparna"],
            },
            {
                "status": "form_set_mismatch",
                "upos": "VERB",
                "lemma": "göra",
                "extra_from_saol": [],
                "missing_from_saol": [],
            },
            {"status": "exact_form_set", "upos": "NOUN", "lemma": "bord"},
        ]

        summary = analyse_rows(rows, examples=1)

        self.assertEqual(3, summary["remaining_form_mismatches_total"])
        self.assertEqual(2, summary["remaining_noun_form_mismatches"])
        self.assertEqual(1, summary["remaining_non_noun_form_mismatches"])
        self.assertEqual(1, summary["noun_mismatch_groups"])
        group = summary["groups"][0]
        self.assertEqual(2, group["count"])
        self.assertEqual(["+et", "+ets"], group["extra_pattern"])
        self.assertEqual(["+ar", "+arna"], group["missing_pattern"])
        self.assertEqual("chatt", group["examples"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
