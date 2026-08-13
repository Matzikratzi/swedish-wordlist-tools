from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_vasen_variant_mismatches import (
    TARGET_NOTATION,
    analyze_rows,
)


class AnalyzeVasenVariantMismatchesTests(unittest.TestCase):
    def test_selects_only_unclassified_noun_target_notation(self) -> None:
        rows = [
            {
                "lemma": "bankväsen",
                "record_id": "5598",
                "homonym_number": "1",
                "upos": "NOUN",
                "notation": TARGET_NOTATION,
                "mismatch_classification": "unclassified",
                "coverage_status": "full",
                "paradigm_status": "form_set_mismatch",
                "paradigm_reason": "primary_paradigm_difference",
                "match_method": "article_variant_lemmas_same_upos",
                "saol_variant_lemmas": ["bankväsen", "bankväsende"],
                "generated_forms": ["bankväsen", "bankväsendet"],
                "saldo_forms": ["bankväsen", "bankväsendet"],
                "extra_from_saol": ["bankväsende"],
                "missing_from_saol": [],
                "variant_validation": [
                    {
                        "lemma": "bankväsen",
                        "heading_type": "primary",
                        "status": "exact_form_set",
                        "generated_forms": ["bankväsen"],
                        "saldo_forms": ["bankväsen"],
                        "extra_from_saol": [],
                        "missing_from_saol": [],
                    }
                ],
            },
            {
                "lemma": "other",
                "record_id": "2",
                "upos": "NOUN",
                "notation": "+en +er",
                "mismatch_classification": "unclassified",
            },
            {
                "lemma": "classified",
                "record_id": "3",
                "upos": "NOUN",
                "notation": TARGET_NOTATION,
                "mismatch_classification": "saldo_missing_plural",
            },
            {
                "lemma": "adjective",
                "record_id": "4",
                "upos": "ADJ",
                "notation": TARGET_NOTATION,
                "mismatch_classification": "unclassified",
            },
        ]

        summary = analyze_rows(rows)

        self.assertEqual(1, summary["rows"])
        self.assertEqual(1, summary["unique_record_ids"])
        self.assertEqual({"1": 1}, summary["homonym_counts"])
        self.assertEqual({"exact_form_set": 1}, summary["variant_status_counts"])
        self.assertEqual("bankväsen", summary["details"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
