from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_pattern_mismatches import analyse_rows


class AnalyzeNounPatternMismatchesTests(unittest.TestCase):
    def test_filters_exact_noun_notation_and_groups_relative_differences(self) -> None:
        rows = [
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "notation": "+en +er",
                "lemma": "banan",
                "homonym_number": "1",
                "generated_forms": ["banan", "bananen", "bananer", "bananerna", "banans"],
                "saldo_forms": ["banan", "bananen", "bananer", "bananerna"],
                "extra_from_saol": ["banans"],
                "missing_from_saol": [],
            },
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "notation": "+en +er",
                "lemma": "kanon",
                "homonym_number": "2",
                "generated_forms": ["kanon", "kanonen", "kanoner", "kanonerna", "kanons"],
                "saldo_forms": ["kanon", "kanonen", "kanoner", "kanonerna"],
                "extra_from_saol": ["kanons"],
                "missing_from_saol": [],
            },
            {
                "upos": "ADJ",
                "status": "form_set_mismatch",
                "notation": "+en +er",
                "lemma": "annan",
                "extra_from_saol": ["annans"],
                "missing_from_saol": [],
            },
            {
                "upos": "NOUN",
                "status": "saol_forms_are_subset",
                "notation": "+en +er",
                "lemma": "citron",
                "extra_from_saol": [],
                "missing_from_saol": ["citronens"],
            },
            {
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "notation": "+en +ar",
                "lemma": "flicka",
                "extra_from_saol": ["flickas"],
                "missing_from_saol": [],
            },
        ]

        report = analyse_rows(rows)

        self.assertEqual(2, report["records"])
        self.assertEqual({"extra_only": 2}, report["direction_counts"])
        self.assertEqual(1, len(report["groups"]))
        self.assertEqual(2, report["groups"][0]["count"])
        self.assertEqual(["+s"], report["groups"][0]["extra_pattern"])
        self.assertEqual([], report["groups"][0]["missing_pattern"])
        self.assertEqual(
            ["banan", "kanon"],
            [item["lemma"] for item in report["groups"][0]["examples"]],
        )

    def test_reports_both_sides_of_a_mismatch(self) -> None:
        report = analyse_rows(
            [
                {
                    "upos": "NOUN",
                    "status": "form_set_mismatch",
                    "notation": "+en +er",
                    "lemma": "motor",
                    "extra_from_saol": ["motorers"],
                    "missing_from_saol": ["motorernas"],
                }
            ]
        )

        self.assertEqual({"both": 1}, report["direction_counts"])
        self.assertEqual(["+ers"], report["groups"][0]["extra_pattern"])
        self.assertEqual(["+ernas"], report["groups"][0]["missing_pattern"])


if __name__ == "__main__":
    unittest.main()
