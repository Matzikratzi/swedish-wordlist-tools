from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_top_noun_mismatch_groups import analyse


class AnalyzeTopNounMismatchGroupsTests(unittest.TestCase):
    def test_reports_other_saol_lexeme_overlap(self) -> None:
        validation = [{
            "record_id": "hajk-noun",
            "lemma": "hajk",
            "homonym_number": "1",
            "upos": "NOUN",
            "status": "form_set_mismatch",
            "notation": "+en +er",
            "generated_forms": ["hajk", "hajken", "hajker"],
            "saldo_forms": ["hajk", "hajken", "hajkar", "hajkars"],
            "extra_from_saol": ["hajker"],
            "missing_from_saol": ["hajkar", "hajkars"],
        }]
        saol = [
            {
                "id": "hajk-noun",
                "normaliserat_ord": "hajk",
                "upos": "NOUN",
                "ordkl": "subst.",
                "text": "+en +er",
            },
            {
                "id": "hajka-verb",
                "normaliserat_ord": "hajka",
                "upos": "VERB",
                "ordkl": "verb",
                "text": "-r -de -t",
            },
        ]
        saldo = {
            "hajk": [{
                "id": "hajk..nn.1",
                "upos": "NOUN",
                "lemmas": {"hajk"},
                "forms": {"hajk", "hajken", "hajkar", "hajkars"},
            }]
        }

        summary = analyse(validation, saol, saldo, top_groups=1)

        self.assertEqual(1, summary["remaining_noun_mismatches"])
        entry = summary["groups"][0]["entries"][0]
        self.assertEqual("hajk", entry["lemma"])
        self.assertEqual("hajka", entry["other_saol_entries"][0]["lemma"])
        self.assertIn("hajkar", entry["other_saol_entries"][0]["overlapping_missing_forms"])

    def test_limits_number_of_groups(self) -> None:
        rows = [
            {
                "record_id": str(index),
                "lemma": lemma,
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "generated_forms": [lemma, lemma + extra],
                "saldo_forms": [lemma, lemma + missing],
                "extra_from_saol": [lemma + extra],
                "missing_from_saol": [lemma + missing],
            }
            for index, (lemma, extra, missing) in enumerate((
                ("a", "x", "y"),
                ("b", "x", "y"),
                ("c", "q", "z"),
            ))
        ]

        summary = analyse(rows, [], {}, top_groups=1)

        self.assertEqual(2, summary["total_groups"])
        self.assertEqual(1, summary["reported_groups"])
        self.assertEqual(2, summary["groups"][0]["count"])


if __name__ == "__main__":
    unittest.main()
