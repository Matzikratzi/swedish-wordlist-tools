from __future__ import annotations

import unittest

from swedish_wordlist_tools.refine_noun_semantic_differences import classify_form


class ExplicitFormCutAndSpliceTests(unittest.TestCase):
    def test_classifies_arbitrary_cut_and_splice_damage(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "added_forms": ["alpha-beta-delta"],
            "change_reasons": {"alpha-beta-delta": "explicit"},
        }
        self.assertEqual(
            "legacy_explicit_form_error",
            classify_form(row, "alpha-beta-gammelta"),
        )

    def test_classifies_tio_i_topp_shape_without_word_rule(self) -> None:
        row = {
            "lemma": "tio-i-topp-lista",
            "added_forms": ["tio-i-topp-listor"],
            "change_reasons": {"tio-i-topp-listor": "explicit"},
        }
        self.assertEqual(
            "legacy_explicit_form_error",
            classify_form(row, "tio-i-topp-listopp"),
        )

    def test_requires_explicit_provenance(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "added_forms": ["alpha-beta-delta"],
            "change_reasons": {"alpha-beta-delta": "append"},
        }
        self.assertEqual(
            "review_required",
            classify_form(row, "alpha-beta-gammelta"),
        )

    def test_does_not_classify_source_forms_themselves(self) -> None:
        row = {
            "lemma": "alpha-beta-gamma",
            "added_forms": ["alpha-beta-delta"],
            "change_reasons": {"alpha-beta-delta": "explicit"},
        }
        self.assertEqual("review_required", classify_form(row, "alpha-beta-gamma"))
        self.assertEqual("review_required", classify_form(row, "alpha-beta-delta"))


if __name__ == "__main__":
    unittest.main()
