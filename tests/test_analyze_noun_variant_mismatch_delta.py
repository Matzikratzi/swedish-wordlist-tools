from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_variant_mismatch_delta import (
    _compare_rows,
    _strip_variant_metadata,
)


class AnalyzeNounVariantMismatchDeltaTests(unittest.TestCase):
    def test_strip_variant_metadata_keeps_grouped_forms(self) -> None:
        rows = [{
            "lemma": "akne",
            "forms": [{"written_form": "akne"}, {"written_form": "acne"}],
            "variant_lemmas": ["akne", "acne"],
            "variant_paradigms": [{"lemma": "akne"}, {"lemma": "acne"}],
        }]
        stripped = _strip_variant_metadata(rows)
        self.assertEqual(rows[0]["forms"], stripped[0]["forms"])
        self.assertNotIn("variant_lemmas", stripped[0])
        self.assertNotIn("variant_paradigms", stripped[0])

    def test_compare_rows_counts_mismatch_transition(self) -> None:
        base = {
            "record_id": "1", "homonym_number": "1", "lemma": "x",
            "upos": "NOUN", "notation": "+en", "generated_forms": ["x"],
            "saldo_forms": ["x"], "match_method": "lemma_same_upos",
        }
        before = [dict(base, status="exact_form_set")]
        after = [dict(base, status="form_set_mismatch", generated_forms=["x", "xs"])]
        details, transitions = _compare_rows(before, after, stage="variant_form_generation")
        self.assertEqual(1, transitions["exact_form_set->form_set_mismatch"])
        self.assertEqual(1, len(details))
        self.assertEqual("variant_form_generation", details[0]["stage"])

    def test_compare_rows_treats_new_match_explicitly(self) -> None:
        after = [{
            "record_id": "2", "homonym_number": "1", "lemma": "y",
            "upos": "NOUN", "notation": "+en", "generated_forms": ["y"],
            "saldo_forms": ["y", "ys"], "match_method": "article_variant_lemmas_same_upos_partial",
            "status": "form_set_mismatch",
        }]
        details, transitions = _compare_rows([], after, stage="article_variant_matching")
        self.assertEqual(1, transitions["no_match->form_set_mismatch"])
        self.assertEqual("no_match", details[0]["before_status"])


if __name__ == "__main__":
    unittest.main()
