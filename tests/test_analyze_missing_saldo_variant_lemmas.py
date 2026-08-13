from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_missing_saldo_variant_lemmas import classify, relation


class AnalyzeMissingSaldoVariantLemmasTests(unittest.TestCase):
    def test_relations_cover_common_variant_spelling_patterns(self) -> None:
        self.assertEqual("same_as_article_lemma", relation("afterwork", "afterwork"))
        self.assertEqual("spacing_or_hyphen_only", relation("afterwork", "after work"))
        self.assertEqual("case_only", relation("DNA", "dna"))
        self.assertEqual("edit_distance_1", relation("akne", "acne"))

    def test_separates_whole_article_missing_from_partial_variant_missing(self) -> None:
        rows = [
            {
                "record_id": "1", "homonym_number": "1", "article_lemma": "afterwork",
                "variant_lemma": "afterwork", "variant_mode": "shared_notation", "status": "missing",
                "saol_forms": ["afterwork"],
            },
            {
                "record_id": "1", "homonym_number": "1", "article_lemma": "afterwork",
                "variant_lemma": "after work", "variant_mode": "shared_notation", "status": "missing",
                "saol_forms": ["after work"],
            },
            {
                "record_id": "2", "homonym_number": "1", "article_lemma": "abrovink",
                "variant_lemma": "abrovink", "variant_mode": "shared_notation", "status": "exact",
                "saol_forms": ["abrovink"],
            },
            {
                "record_id": "2", "homonym_number": "1", "article_lemma": "abrovink",
                "variant_lemma": "abrovinsch", "variant_mode": "shared_notation", "status": "missing",
                "saol_forms": ["abrovinsch"],
            },
        ]
        classified, summary = classify(rows)
        self.assertEqual(3, summary["missing_variant_paradigms"])
        self.assertEqual(2, summary["affected_articles"])
        self.assertEqual(1, summary["articles_all_variants_missing"])
        self.assertEqual(1, summary["articles_with_some_saldo_match"])
        afterwork = [row for row in classified if row["record_id"] == "1"]
        self.assertTrue(all(row["article_all_variants_missing"] for row in afterwork))
        abrovinsch = next(row for row in classified if row["variant_lemma"] == "abrovinsch")
        self.assertTrue(abrovinsch["article_has_other_saldo_match"])
        self.assertFalse(abrovinsch["article_all_variants_missing"])


if __name__ == "__main__":
    unittest.main()
