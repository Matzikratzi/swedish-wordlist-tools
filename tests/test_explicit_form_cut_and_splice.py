from __future__ import annotations

import unittest

from swedish_wordlist_tools.refine_noun_semantic_differences import classify_form


class ExplicitFormCutAndSpliceTests(unittest.TestCase):
    def test_classifies_arbitrary_hyphen_token_damage(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "notation": "+n alpha-beta-melta",
            "added_forms": ["alpha-beta-melta"],
            "change_reasons": {"alpha-beta-melta": "explicit"},
        }
        self.assertEqual(
            "legacy_explicit_form_error",
            classify_form(row, "alpha-beta-gammelta"),
        )

    def test_classifies_tio_i_topp_shape_without_word_rule(self) -> None:
        row = {
            "lemma": "tio-i-topp-lista",
            "notation": "+n tio-i-topp-listor",
            "added_forms": [],
            "change_reasons": {},
        }
        self.assertEqual(
            "legacy_explicit_form_error",
            classify_form(row, "tio-i-topp-listopp"),
        )

    def test_reads_explicit_form_even_when_not_added(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "notation": "+n alpha-beta-melta",
            "added_forms": [],
            "change_reasons": {},
        }
        self.assertEqual(
            "legacy_explicit_form_error",
            classify_form(row, "alpha-beta-gammelta"),
        )

    def test_requires_explicit_provenance(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "notation": "+n +melta",
            "added_forms": ["alpha-beta-melta"],
            "change_reasons": {"alpha-beta-melta": "append"},
        }
        self.assertEqual(
            "review_required",
            classify_form(row, "alpha-beta-gammelta"),
        )

    def test_does_not_classify_source_forms_themselves(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "notation": "+n alpha-beta-melta",
            "added_forms": [],
            "change_reasons": {},
        }
        self.assertEqual("review_required", classify_form(row, "alpha-beta-gamma"))
        self.assertEqual("review_required", classify_form(row, "alpha-beta-melta"))


if __name__ == "__main__":
    unittest.main()
