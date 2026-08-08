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
        self.assertEqual({"not_applicable": 1}, summary["coverage_status_counts"])
        self.assertEqual(1, len(summary["groups"]))
        group = summary["groups"][0]
        self.assertEqual(["+erna"], group["extra_pattern"])
        self.assertEqual(["+ar"], group["missing_pattern"])

    def test_partial_variant_coverage_with_exact_present_paradigm_is_not_mismatch(self) -> None:
        summary = analyse_rows([
            {
                "status": "form_set_mismatch",
                "lemma": "alisarin",
                "upos": "NOUN",
                "notation": "+et",
                "match_method": "article_variant_lemmas_same_upos_partial",
                "variant_validation": [
                    {"lemma": "alisarin", "heading_type": "primary", "status": "exact_form_set"},
                    {"lemma": "alizarin", "heading_type": "alternative", "status": "variant_missing_in_saldo"},
                ],
                "extra_from_saol": ["alizarin"],
                "missing_from_saol": [],
            }
        ])
        self.assertEqual(0, summary["records"])

    def test_partial_variant_coverage_with_real_present_paradigm_mismatch_is_kept(self) -> None:
        summary = analyse_rows([
            {
                "status": "form_set_mismatch",
                "lemma": "chipp",
                "upos": "NOUN",
                "notation": "+et +ar",
                "match_method": "article_variant_lemmas_same_upos_partial",
                "variant_validation": [
                    {"lemma": "chipp", "heading_type": "primary", "status": "form_set_mismatch"},
                    {"lemma": "chip", "heading_type": "alternative", "status": "variant_missing_in_saldo"},
                ],
                "extra_from_saol": ["chip"],
                "missing_from_saol": ["chippar"],
            }
        ])
        self.assertEqual(1, summary["records"])
        self.assertEqual({"partial": 1}, summary["coverage_status_counts"])
        self.assertEqual({"primary_paradigm_difference": 1}, summary["paradigm_reason_counts"])

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

    def test_materialized_axis_values_are_used_when_present(self) -> None:
        summary = analyse_rows([
            {
                "status": "form_set_mismatch",
                "coverage_status": "partial",
                "paradigm_status": "exact_form_set",
                "paradigm_reason": "all_present_variants_exact",
                "lemma": "foo",
                "upos": "NOUN",
                "notation": "+en",
                "match_method": "article_variant_lemmas_same_upos_partial",
                "extra_from_saol": ["foe"],
                "missing_from_saol": [],
            }
        ])
        self.assertEqual(0, summary["records"])

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
        self.assertIn("Urval: paradigm_status=form_set_mismatch", text)
        self.assertIn("Per ordklass:", text)
        self.assertIn("Per varianttäckning:", text)
        self.assertIn("lemma_same_upos", text)
        self.assertIn("hund (2)", text)


if __name__ == "__main__":
    unittest.main()
