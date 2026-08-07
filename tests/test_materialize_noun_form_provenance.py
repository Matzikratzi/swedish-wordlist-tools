from __future__ import annotations

import unittest

from swedish_wordlist_tools.materialize_noun_form_provenance import materialize
from swedish_wordlist_tools.noun_form_provenance import enrich_form


class MaterializeNounFormProvenanceTests(unittest.TestCase):
    def test_single_primary_source_becomes_generated_from(self) -> None:
        form = enrich_form({
            "written_form": "brevbäringen",
            "article_id": "9875",
            "heading": "brevbäring",
            "variant_source": "primary",
            "variant_mode": "shared_notation",
            "variant_lemma": "brevbäring",
            "variant_sources": [
                {
                    "heading": "brevbäring",
                    "variant_lemma": "brevbäring",
                    "variant_source": "primary",
                }
            ],
        })
        self.assertEqual(
            [{
                "article_id": "9875",
                "heading": "brevbäring",
                "heading_type": "primary",
                "variant_lemma": "brevbäring",
                "variant_mode": "shared_notation",
            }],
            form["generated_from"],
        )

    def test_merged_form_retains_both_exact_heading_sources(self) -> None:
        form = enrich_form({
            "written_form": "bankväsendet",
            "article_id": "5598",
            "variant_source": "merged",
            "variant_mode": "parallel_branches",
            "variant_sources": [
                {
                    "heading": "bankväsen",
                    "variant_lemma": "bankväsen",
                    "variant_source": "primary",
                },
                {
                    "heading": "bankväsende",
                    "variant_lemma": "bankväsende",
                    "variant_source": "alternative",
                },
            ],
        })
        self.assertEqual(
            {("5598", "bankväsen", "primary"), ("5598", "bankväsende", "alternative")},
            {
                (item["article_id"], item["heading"], item["heading_type"])
                for item in form["generated_from"]
            },
        )

    def test_materialization_is_form_set_neutral(self) -> None:
        rows = [{
            "record_id": "7",
            "lemma": "bil",
            "forms": [
                {
                    "written_form": "bil",
                    "article_id": "7",
                    "heading": "bil",
                    "variant_source": "primary",
                    "variant_mode": "single",
                    "variant_lemma": "bil",
                },
                {
                    "written_form": "bilen",
                    "article_id": "7",
                    "heading": "bil",
                    "variant_source": "primary",
                    "variant_mode": "single",
                    "variant_lemma": "bil",
                },
            ],
        }]
        enriched, summary = materialize(rows)
        self.assertTrue(summary["written_form_signature_unchanged"])
        self.assertEqual(2, summary["forms"])
        self.assertEqual(2, summary["generated_from_records"])
        self.assertEqual(["bil", "bilen"], [form["written_form"] for form in enriched[0]["forms"]])
        self.assertTrue(all(form["generated_from"] for form in enriched[0]["forms"]))


if __name__ == "__main__":
    unittest.main()
