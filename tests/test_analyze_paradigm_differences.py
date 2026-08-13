from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_paradigm_differences import analyse_rows


class AnalyzeParadigmDifferencesTests(unittest.TestCase):
    def test_groups_by_notation_and_relative_form_patterns(self) -> None:
        rows = [
            {
                "status": "saol_paradigm_differs_from_saldo",
                "lemma": "medley",
                "homonym_number": "2",
                "notation": "+t +n",
                "extra_from_saol": ["medleyt", "medleyts", "medleyna", "medleynas"],
                "missing_from_saol": [],
                "saldo_lemmas": ["medley"],
            },
            {
                "status": "saol_paradigm_differs_from_saldo",
                "lemma": "ego",
                "homonym_number": "1",
                "notation": "+t +n",
                "extra_from_saol": ["egot", "egots", "egona", "egonas"],
                "missing_from_saol": [],
                "saldo_lemmas": ["ego"],
            },
            {
                "status": "exact_form_set",
                "lemma": "demo",
                "homonym_number": "1",
                "notation": "+n; pl. +",
                "extra_from_saol": [],
                "missing_from_saol": [],
                "saldo_lemmas": ["demo"],
            },
        ]

        summary = analyse_rows(rows)

        self.assertEqual(2, summary["records"])
        self.assertEqual({"+t +n": 2}, summary["notation_counts"])
        self.assertEqual(1, len(summary["groups"]))
        group = summary["groups"][0]
        self.assertEqual(2, group["count"])
        self.assertEqual(["+na", "+nas", "+t", "+ts"], group["extra_pattern"])
        self.assertEqual(["ego", "medley"], [item["lemma"] for item in group["examples"]])

    def test_keeps_non_suffix_forms_separate(self) -> None:
        rows = [
            {
                "status": "saol_paradigm_differs_from_saldo",
                "lemma": "feromon",
                "homonym_number": "1",
                "notation": "+et +er",
                "extra_from_saol": ["feromonet"],
                "missing_from_saol": ["feromonen"],
                "saldo_lemmas": ["feromon"],
            }
        ]

        summary = analyse_rows(rows)
        group = summary["groups"][0]
        self.assertEqual(["+et"], group["extra_pattern"])
        self.assertEqual(["+en"], group["missing_pattern"])


if __name__ == "__main__":
    unittest.main()
