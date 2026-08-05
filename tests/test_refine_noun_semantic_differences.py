from __future__ import annotations

import unittest

from swedish_wordlist_tools.refine_noun_semantic_differences import (
    build_review,
    classify_form,
)


class RefineNounSemanticDifferencesTests(unittest.TestCase):
    def test_classifies_stycke_guided_tail_errors(self) -> None:
        for row, form in (
            (
                {
                    "lemma": "adressregister",
                    "stycke": "adress|reg·ister",
                    "added_forms": ["adressregistren", "adressregistret"],
                    "change_reasons": {
                        "adressregistren": "replace_tail",
                        "adressregistret": "replace_tail",
                    },
                },
                "adressregisteregistren",
            ),
            (
                {
                    "lemma": "armémuseum",
                    "stycke": "armé|muse·um",
                    "added_forms": ["armémuseer", "armémuseet"],
                    "change_reasons": {
                        "armémuseer": "replace_tail",
                        "armémuseet": "replace_tail",
                    },
                },
                "armémuseumuseer",
            ),
        ):
            with self.subTest(form=form):
                self.assertEqual("legacy_stycke_tail_error", classify_form(row, form))

    def test_classifies_lexicographic_labels(self) -> None:
        for label in ("ibl", "vard", "högt"):
            with self.subTest(label=label):
                self.assertEqual(
                    "legacy_lexicographic_label",
                    classify_form({}, label),
                )

    def test_keeps_unexplained_forms_for_review(self) -> None:
        row = {
            "lemma": "abc",
            "stycke": "abc",
            "added_forms": ["abc:n"],
            "change_reasons": {"abc:n": "explicit"},
        }
        self.assertEqual("review_required", classify_form(row, "n"))

    def test_builds_reduced_review(self) -> None:
        review = build_review(
            [
                {
                    "record_id": "1",
                    "lemma": "adressregister",
                    "notation": "-registret; pl. +, best. pl. -registren",
                    "stycke": "adress|reg·ister",
                    "semantic_removed_forms": [
                        "adressregisteregistren",
                        "adressregisteregistret",
                    ],
                    "added_forms": ["adressregistren", "adressregistret"],
                    "change_reasons": {
                        "adressregistren": "replace_tail",
                        "adressregistret": "replace_tail",
                    },
                },
                {
                    "record_id": "2",
                    "lemma": "meter",
                    "notation": "+n; pl. + ibl. -metrar",
                    "stycke": "meter",
                    "semantic_removed_forms": ["ibl"],
                    "added_forms": ["metrar"],
                    "change_reasons": {"metrar": "replace_tail"},
                },
                {
                    "record_id": "3",
                    "lemma": "abc",
                    "notation": "abc:et; pl. abc:n",
                    "stycke": "abc",
                    "semantic_removed_forms": ["n"],
                    "added_forms": ["abc:n"],
                    "change_reasons": {"abc:n": "explicit"},
                },
            ]
        )
        self.assertEqual(3, review["semantic_rows"])
        self.assertEqual(1, review["review_required_rows"])
        self.assertEqual(1, review["review_required_forms"])
        self.assertEqual("abc", review["rows"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
