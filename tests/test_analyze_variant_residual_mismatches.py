from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_variant_residual_mismatches import build_residuals


class AnalyzeVariantResidualMismatchesTests(unittest.TestCase):
    def test_separates_new_residual_rows_from_net_delta_and_collapses_article_duplicates(self) -> None:
        delta_summary = {
            "legacy_form_set_mismatch": 10,
            "current_form_set_mismatch": 11,
            "net_delta": 1,
        }
        common = {
            "stage": "net",
            "record_id": "10",
            "lemma": "foo",
            "upos": "NOUN",
            "notation": "+en +ar",
            "before_status": "exact_form_set",
            "after_status": "form_set_mismatch",
            "before_generated_forms": ["foo"],
            "after_generated_forms": ["foo", "foe"],
            "before_saldo_forms": ["foo"],
            "after_saldo_forms": ["foo"],
            "before_match_method": "lemma_same_upos",
            "after_match_method": "article_variant_lemmas_same_upos_partial",
        }
        details = [
            dict(common, homonym_number="1"),
            dict(common, homonym_number="0"),
            {
                "stage": "net",
                "record_id": "20",
                "homonym_number": "1",
                "lemma": "bar",
                "upos": "NOUN",
                "notation": "+en +ar",
                "before_status": "form_set_mismatch",
                "after_status": "exact_form_set",
                "before_generated_forms": ["bar", "bars"],
                "after_generated_forms": ["bar"],
                "before_saldo_forms": ["bar"],
                "after_saldo_forms": ["bar"],
                "before_match_method": "lemma_same_upos",
                "after_match_method": "article_variant_lemmas_same_upos",
            },
        ]
        noun_rows = [
            {
                "record_id": "10",
                "article_id": "10",
                "lemma": "foo",
                "variant_mode": "shared_notation",
                "variant_lemmas": ["foo", "foe"],
                "forms": [
                    {
                        "written_form": "foo",
                        "variant_source": "primary",
                        "variant_sources": [
                            {"heading": "foo", "variant_lemma": "foo", "variant_source": "primary"}
                        ],
                    },
                    {
                        "written_form": "foe",
                        "variant_source": "alternative",
                        "variant_sources": [
                            {"heading": "foe", "variant_lemma": "foe", "variant_source": "alternative"}
                        ],
                    },
                ],
            }
        ]
        summary, rows = build_residuals(delta_summary, details, noun_rows)
        self.assertEqual(2, summary["new_residual_validation_rows"])
        self.assertEqual(1, summary["resolved_legacy_mismatch_rows"])
        self.assertEqual(1, summary["net_delta"])
        self.assertTrue(summary["net_identity_holds"])
        self.assertEqual(1, summary["new_residual_articles"])
        self.assertEqual(1, len(rows))
        self.assertEqual(["0", "1"], rows[0]["homonym_numbers"])
        self.assertEqual(2, rows[0]["validation_rows"])
        self.assertEqual("partial_variant_saldo_coverage", rows[0]["reason"])
        self.assertEqual("alternative", rows[0]["extra_form_provenance"]["foe"][0]["variant_source"])

    def test_full_match_with_alternative_only_extra_gets_specific_reason(self) -> None:
        delta_summary = {
            "legacy_form_set_mismatch": 0,
            "current_form_set_mismatch": 1,
            "net_delta": 1,
        }
        details = [
            {
                "stage": "net",
                "record_id": "30",
                "homonym_number": "1",
                "lemma": "alpha",
                "upos": "NOUN",
                "notation": "+n",
                "before_status": "exact_form_set",
                "after_status": "form_set_mismatch",
                "before_generated_forms": ["alpha"],
                "after_generated_forms": ["alpha", "alfa"],
                "before_saldo_forms": ["alpha"],
                "after_saldo_forms": ["alpha"],
                "before_match_method": "lemma_same_upos",
                "after_match_method": "article_variant_lemmas_same_upos",
            }
        ]
        noun_rows = [
            {
                "record_id": "30",
                "article_id": "30",
                "lemma": "alpha",
                "variant_mode": "shared_notation",
                "variant_lemmas": ["alpha", "alfa"],
                "forms": [
                    {"written_form": "alpha", "variant_sources": [{"heading": "alpha", "variant_lemma": "alpha", "variant_source": "primary"}]},
                    {"written_form": "alfa", "variant_sources": [{"heading": "alfa", "variant_lemma": "alfa", "variant_source": "alternative"}]},
                ],
            }
        ]
        summary, rows = build_residuals(delta_summary, details, noun_rows)
        self.assertTrue(summary["net_identity_holds"])
        self.assertEqual("alternative_variant_forms_not_in_saldo", rows[0]["reason"])


if __name__ == "__main__":
    unittest.main()
