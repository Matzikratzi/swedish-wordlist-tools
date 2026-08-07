from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_form_mismatches import analyse_rows, render_text


class AnalyzeFormMismatchesTests(unittest.TestCase):
    def test_groups_only_real_form_mismatches(self) -> None:
        rows = [
            {
                "status": "form_set_mismatch",
                "lemma": "katt",
                "homonym_number": "1",
                "upos": "NOUN",
                "notation": "+en +er",
                "match_method": "lemma_same_upos",
                "extra_from_saol": ["katterna"],
                "missing_from_saol": ["kattar"],
                "saldo_lemmas": ["katt"],
            },
            {
                "status": "saldo_form_match_other_lexeme",
                "lemma": "fälle",
                "upos": "NOUN",
                "notation": "+t +n",
                "match_method": "unique_form_same_upos",
                "extra_from_saol": ["fället"],
                "missing_from_saol": ["fälla"],
            },
        ]
        summary = analyse_rows(rows)
        self.assertEqual(1, summary["records"])
        self.assertEqual({"NOUN": 1}, summary["upos_counts"])
        self.assertEqual(1, len(summary["groups"]))
        group = summary["groups"][0]
        self.assertEqual(["+erna"], group["extra_pattern"])
        self.assertEqual(["+ar"], group["missing_pattern"])

    def test_exact_form_set_never_becomes_a_mismatch(self) -> None:
        summary = analyse_rows(
            [
                {
                    "status": "exact_form_set",
                    "lemma": "bandage",
                    "homonym_number": "1",
                    "upos": "NOUN",
                    "notation": "+t [-et]; pl. +",
                    "match_method": "lemma_same_upos",
                    "generated_forms": [
                        "bandage",
                        "bandagen",
                        "bandagens",
                        "bandages",
                        "bandaget",
                        "bandagets",
                    ],
                    "saldo_forms": [
                        "bandage",
                        "bandagen",
                        "bandagens",
                        "bandages",
                        "bandaget",
                        "bandagets",
                    ],
                    "extra_from_saol": [],
                    "missing_from_saol": [],
                }
            ]
        )
        self.assertEqual(0, summary["records"])
        self.assertEqual({}, summary["upos_counts"])
        self.assertEqual([], summary["groups"])

    def test_renders_dimensions_and_examples(self) -> None:
        summary = analyse_rows([
            {
                "status": "form_set_mismatch",
                "lemma": "hund",
                "homonym_number": "2",
                "upos": "NOUN",
                "notation": "+en +ar",
                "match_method": "lemma_same_upos",
                "extra_from_saol": ["hundar"],
                "missing_from_saol": ["hunder"],
                "saldo_lemmas": ["hund"],
            }
        ])
        text = render_text(summary)
        self.assertIn("Per ordklass:", text)
        self.assertIn("Per SAOL-notation:", text)
        self.assertIn("lemma_same_upos", text)
        self.assertIn("hund (2)", text)


if __name__ == "__main__":
    unittest.main()
