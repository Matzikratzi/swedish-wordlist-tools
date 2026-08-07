from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_missing_noun_variant_saldo_evidence import classify_missing_variants


class AnalyzeMissingNounVariantSaldoEvidenceTests(unittest.TestCase):
    def test_separator_only_candidate_is_classified_as_orthographic(self) -> None:
        alignment = [{
            "article_id": "1",
            "article_lemma": "afterwork",
            "variant_mode": "shared_notation",
            "variants": [{
                "lemma": "after work",
                "status": "missing",
                "saol_forms": ["after work", "after worken"],
            }],
        }]
        saldo = {
            "after-work": [{
                "id": "a",
                "upos": "NOUN",
                "lemmas": {"after-work"},
                "forms": {"after-work", "after-worken"},
            }]
        }
        rows, summary = classify_missing_variants(alignment, saldo)
        self.assertEqual("orthographic_saldo_candidate", rows[0]["classification"])
        self.assertEqual("separator_only", rows[0]["orthographic_kind"])
        self.assertEqual(["after-work"], rows[0]["orthographic_candidates"])
        self.assertEqual(1, summary["classification_counts"]["orthographic_saldo_candidate"])

    def test_strong_form_evidence_under_other_lemma(self) -> None:
        alignment = [{
            "article_id": "2",
            "article_lemma": "foo",
            "variant_mode": "shared_notation",
            "variants": [{
                "lemma": "foox",
                "status": "missing",
                "saol_forms": ["foox", "foona", "foonas", "foons"],
            }],
        }]
        saldo = {
            "bar": [{
                "id": "b",
                "upos": "NOUN",
                "lemmas": {"bar"},
                "forms": {"foona", "foonas", "foons"},
            }]
        }
        rows, _summary = classify_missing_variants(alignment, saldo)
        self.assertEqual("strong_other_lemma_form_evidence", rows[0]["classification"])
        self.assertEqual(3, rows[0]["saldo_form_overlap_count"])
        self.assertIn("bar", rows[0]["form_evidence_candidate_lemmas"])

    def test_no_evidence_is_kept_as_gap_candidate(self) -> None:
        alignment = [{
            "article_id": "3",
            "article_lemma": "missing",
            "variant_mode": "shared_notation",
            "variants": [{
                "lemma": "missing",
                "status": "missing",
                "saol_forms": ["missing", "missingen"],
            }],
        }]
        rows, summary = classify_missing_variants(alignment, {})
        self.assertEqual("no_saldo_evidence", rows[0]["classification"])
        self.assertEqual(1, summary["classification_counts"]["no_saldo_evidence"])

    def test_non_missing_variants_are_ignored(self) -> None:
        alignment = [{
            "article_id": "4",
            "article_lemma": "exact",
            "variant_mode": "shared_notation",
            "variants": [{"lemma": "exact", "status": "exact", "saol_forms": ["exact"]}],
        }]
        rows, summary = classify_missing_variants(alignment, {})
        self.assertEqual([], rows)
        self.assertEqual(0, summary["missing_variants"])


if __name__ == "__main__":
    unittest.main()
