from __future__ import annotations

import unittest

from swedish_wordlist_tools.refine_noun_semantic_differences import classify_form


class RefineSourceErrorAndOverflowTests(unittest.TestCase):
    def test_discards_all_nonlemma_forms_for_arbitrary_k_source_error(self) -> None:
        row = {
            "lemma": "grundform",
            "notation": "+n; äldre: <k>annan</k>",
        }
        for form in ("grundformen", "annan", "godtycklig"):
            with self.subTest(form=form):
                self.assertEqual(
                    "source_error_discarded_form",
                    classify_form(row, form),
                )
        self.assertEqual("review_required", classify_form(row, "grundform"))

    def test_does_not_apply_lemma_only_policy_without_k_markup(self) -> None:
        self.assertEqual(
            "review_required",
            classify_form({"lemma": "grundform", "notation": "+en"}, "grundformen"),
        )

    def test_classifies_narrow_field_overflow_artifact(self) -> None:
        notation = "x" * 37 + " abcdefghij-"
        self.assertEqual(50, len(notation))
        row = {"lemma": "prefixabcdefghijk", "notation": notation}
        self.assertEqual(
            "legacy_truncated_overflow_error",
            classify_form(row, "prefixabcdefghijghij"),
        )

    def test_classifies_dagen_efter_overflow_shape(self) -> None:
        notation = "dagen-efter-pillret; pl. +, best. pl. dagen-efter-"
        self.assertEqual(50, len(notation))
        row = {"lemma": "dagen-efter-piller", "notation": notation}
        self.assertEqual(
            "legacy_truncated_overflow_error",
            classify_form(row, "dagen-efter-pillefter"),
        )

    def test_requires_both_field_width_and_final_hyphen(self) -> None:
        for notation in (
            "kort abcdefghij-",
            "x" * 38 + " abcdefghij",
        ):
            with self.subTest(notation=notation):
                self.assertEqual(
                    "review_required",
                    classify_form(
                        {"lemma": "prefixabcdefghijk", "notation": notation},
                        "prefixabcdefghijghij",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
