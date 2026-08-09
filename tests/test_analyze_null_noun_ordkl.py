from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_null_noun_ordkl import build_summary, candidates, render


class AnalyzeNullNounOrdklTests(unittest.TestCase):
    def test_groups_null_notation_nouns_by_ordkl(self) -> None:
        rows = [
            {
                "lemma": "kröken",
                "homonym_number": "",
                "record_id": "1",
                "upos": "NOUN",
                "ordkl": "subst.; best.",
                "notation": "",
                "status": "form_set_mismatch",
                "match_method": "lemma_same_upos",
                "generated_forms": ["kröken", "krökens"],
                "saldo_forms": ["krök", "kröken", "krökar", "krökarna"],
            },
            {
                "lemma": "annan",
                "upos": "NOUN",
                "ordkl": "subst.",
                "notation": "+en",
                "status": "form_set_mismatch",
            },
            {
                "lemma": "verb",
                "upos": "VERB",
                "ordkl": "verb",
                "notation": "",
                "status": "form_set_mismatch",
            },
        ]

        selected = candidates(rows)
        self.assertEqual(["kröken"], [row["lemma"] for row in selected])

        summary = build_summary(selected)
        self.assertEqual(1, summary["records"])
        self.assertEqual(1, summary["ordkl_groups"])
        self.assertEqual("subst.; best.", summary["groups"][0]["ordkl"])
        self.assertIn("kröken", render(summary))

    def test_ignores_null_notation_non_mismatches(self) -> None:
        rows = [
            {
                "lemma": "klar",
                "upos": "NOUN",
                "ordkl": "subst.; best.",
                "notation": "",
                "status": "exact_form_set",
            }
        ]
        self.assertEqual([], candidates(rows))


if __name__ == "__main__":
    unittest.main()
