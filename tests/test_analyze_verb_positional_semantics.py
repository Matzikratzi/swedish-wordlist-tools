from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_positional_semantics import (
    analyze,
    pure_unlabelled_form_tokens,
)


class AnalyzeVerbPositionalSemanticsTests(unittest.TestCase):
    def test_accepts_only_pure_unlabelled_form_atoms(self) -> None:
        self.assertEqual(
            ("+er", "+de", "+t"),
            pure_unlabelled_form_tokens(("+er", ",", "+de", ",", "+t")),
        )
        self.assertIsNone(pure_unlabelled_form_tokens(("+de", ",", "+t", ",", "pres.", "+r")))
        self.assertIsNone(pure_unlabelled_form_tokens(("myste", "H", "mös", ",", "myst")))

    def test_groups_saldo_labels_by_atom_count_and_position(self) -> None:
        records = [
            {
                "normaliserat_ord": "testa",
                "upos": "VERB",
                "text": "testar, testade, testat",
            },
            {
                "normaliserat_ord": "må",
                "upos": "VERB",
                "text": "måtte",
            },
        ]
        labels = {
            "testa": {
                "testar": {"pres aktiv"},
                "testade": {"pret aktiv"},
                "testat": {"sup aktiv"},
            },
            "må": {"måtte": {"pret konj"}},
        }
        summary = analyze(records, labels)
        self.assertEqual({"1": 1, "3": 1}, summary["branch_counts_by_atom_count"])
        groups = {group["atom_count"]: group for group in summary["groups"]}
        self.assertEqual({"pres aktiv": 1}, groups[3]["positions"][0]["saldo_label_counts"])
        self.assertEqual({"pret aktiv": 1}, groups[3]["positions"][1]["saldo_label_counts"])
        self.assertEqual({"sup aktiv": 1}, groups[3]["positions"][2]["saldo_label_counts"])
        self.assertEqual({"pret konj": 1}, groups[1]["positions"][0]["saldo_label_counts"])

    def test_excludes_49_and_50_character_sources(self) -> None:
        records = [
            {"normaliserat_ord": "a", "upos": "VERB", "text": "x" * 49},
            {"normaliserat_ord": "b", "upos": "VERB", "text": "x" * 50},
        ]
        self.assertEqual(0, analyze(records, {})["pure_unlabelled_branches"])


if __name__ == "__main__":
    unittest.main()
