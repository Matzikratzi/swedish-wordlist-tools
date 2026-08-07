from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_article_saldo_alignment import analyze


class AnalyzeNounArticleSaldoAlignmentTests(unittest.TestCase):
    def test_unions_variant_paradigms_and_matching_saldo_analyses(self) -> None:
        noun_rows = [{
            "record_id": "5598",
            "homonym_number": "1",
            "lemma": "bankväsen",
            "variant_mode": "parallel_branches",
            "variant_lemmas": ["bankväsen", "bankväsende"],
            "variant_paradigms": [
                {"lemma": "bankväsen", "forms": [
                    {"written_form": "bankväsen"},
                    {"written_form": "bankväsendet"},
                ]},
                {"lemma": "bankväsende", "forms": [
                    {"written_form": "bankväsende"},
                    {"written_form": "bankväsendet"},
                ]},
            ],
        }]
        saldo = {
            "bankväsen": [{
                "id": "a", "upos": "NOUN", "lemmas": {"bankväsen"},
                "forms": {"bankväsen", "bankväsendet"},
            }],
            "bankväsende": [{
                "id": "b", "upos": "NOUN", "lemmas": {"bankväsende"},
                "forms": {"bankväsende", "bankväsendet"},
            }],
        }
        rows, summary = analyze(noun_rows, saldo)
        self.assertEqual(1, len(rows))
        self.assertEqual("exact", rows[0]["status"])
        self.assertEqual([], rows[0]["missing_variant_lemmas"])
        self.assertEqual(1, summary["status_counts"]["exact"])

    def test_reports_partial_variant_coverage_separately_from_form_status(self) -> None:
        noun_rows = [{
            "record_id": "1",
            "homonym_number": "1",
            "lemma": "foo",
            "variant_mode": "shared_notation",
            "variant_lemmas": ["foo", "foe"],
            "variant_paradigms": [
                {"lemma": "foo", "forms": [{"written_form": "foo"}]},
                {"lemma": "foe", "forms": [{"written_form": "foe"}]},
            ],
        }]
        saldo = {
            "foo": [{"id": "a", "upos": "NOUN", "lemmas": {"foo"}, "forms": {"foo"}}]
        }
        rows, summary = analyze(noun_rows, saldo)
        # SALDO contains only one of the two SAOL forms, so SALDO is the subset.
        self.assertEqual("saldo_subset", rows[0]["status"])
        self.assertEqual(["foe"], rows[0]["missing_variant_lemmas"])
        self.assertEqual(1, summary["variant_coverage_counts"]["some_variants_missing"])


if __name__ == "__main__":
    unittest.main()
