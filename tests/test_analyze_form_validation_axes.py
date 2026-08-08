from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_form_validation_axes import classify_axes


class AnalyzeFormValidationAxesTests(unittest.TestCase):
    def test_brevbaring_style_case_keeps_subset_and_partial_coverage(self) -> None:
        row = {
            "status": "form_set_mismatch",
            "variant_validation": [
                {
                    "lemma": "brevbäring",
                    "heading_type": "primary",
                    "status": "saol_forms_are_subset",
                },
                {
                    "lemma": "brevbärning",
                    "heading_type": "alternative",
                    "status": "variant_missing_in_saldo",
                },
            ],
        }
        coverage, paradigm, reason = classify_axes(row)
        self.assertEqual("partial", coverage)
        self.assertEqual("saol_forms_are_subset", paradigm)
        self.assertEqual("at_least_one_present_variant_is_saol_subset", reason)

    def test_missing_alternative_does_not_hide_primary_form_mismatch(self) -> None:
        row = {
            "status": "form_set_mismatch",
            "variant_validation": [
                {
                    "lemma": "foo",
                    "heading_type": "primary",
                    "status": "form_set_mismatch",
                },
                {
                    "lemma": "foe",
                    "heading_type": "alternative",
                    "status": "variant_missing_in_saldo",
                },
            ],
        }
        coverage, paradigm, reason = classify_axes(row)
        self.assertEqual("partial", coverage)
        self.assertEqual("form_set_mismatch", paradigm)
        self.assertEqual("primary_paradigm_difference", reason)

    def test_non_variant_mismatch_remains_form_mismatch(self) -> None:
        coverage, paradigm, reason = classify_axes({"status": "form_set_mismatch"})
        self.assertEqual("not_applicable", coverage)
        self.assertEqual("form_set_mismatch", paradigm)
        self.assertEqual("non_variant_form_difference", reason)


if __name__ == "__main__":
    unittest.main()
