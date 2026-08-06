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
            (
                {
                    "lemma": "abcdef",
                    "stycke": "abc|def",
                    "added_forms": ["abcXYZ"],
                    "change_reasons": {"abcXYZ": "replace_tail"},
                },
                "abXYZ",
            ),
            (
                {
                    "lemma": "abcdef",
                    "stycke": "abc|def",
                    "added_forms": ["abcXYZ"],
                    "change_reasons": {"abcXYZ": "replace_tail"},
                },
                "abcdeXYZ",
            ),
        ):
            with self.subTest(form=form):
                self.assertEqual("legacy_stycke_tail_error", classify_form(row, form))

    def test_does_not_classify_correct_stycke_replacement_as_old_error(self) -> None:
        row = {
            "lemma": "abcdef",
            "stycke": "abc|def",
            "added_forms": ["abcXYZ"],
            "change_reasons": {"abcXYZ": "replace_tail"},
        }
        self.assertEqual("review_required", classify_form(row, "abcXYZ"))

    def test_does_not_guess_stycke_errors_without_replace_tail_provenance(self) -> None:
        row = {
            "lemma": "abcdef",
            "stycke": "abc|def",
            "added_forms": ["abcXYZ"],
            "change_reasons": {"abcXYZ": "explicit"},
        }
        self.assertEqual("review_required", classify_form(row, "abXYZ"))

    def test_classifies_metadata_from_the_rows_own_notation(self) -> None:
        cases = (
            ({"notation": "+n; pl. + ibl. -metrar"}, "ibl"),
            ({"notation": "+en om: gipsförband: ibl. +et; pl. +er"}, "gipsförband"),
            ({"notation": "+n; pl. + el. (mest: om: enstaka: mynt:) rubler"}, "mest"),
            ({"notation": "+t; pl. +n el. (mest: i: fråga: om: musik:) tempi"}, "musik"),
            ({"notation": "+en; som: måttord: pl. +"}, "måttord"),
        )
        for row, form in cases:
            with self.subTest(form=form):
                self.assertEqual(
                    "legacy_notation_metadata",
                    classify_form(row, form),
                )

    def test_classifies_arbitrary_colon_final_tokens_structurally(self) -> None:
        cases = (
            ("xqz:", "xqz"),
            ("123abc:", "123abc"),
            ("räksmörgås:", "räksmörgås"),
            ("ÅÄÖ:", "ÅÄÖ"),
        )
        for token, removed_form in cases:
            with self.subTest(token=token):
                self.assertEqual(
                    "legacy_notation_metadata",
                    classify_form({"notation": f"+n; {token} +ar"}, removed_form),
                )

    def test_classifies_suffixes_split_from_internal_colons(self) -> None:
        for notation, fragment in (
            ("+:qz +:ar", "qz"),
            ("ABC:qz; pl. ABC:ar", "qz"),
            ("abc:na", "na"),
            ("BB:t; pl. BB:n", "t"),
        ):
            with self.subTest(notation=notation, fragment=fragment):
                self.assertEqual(
                    "legacy_colon_fragment",
                    classify_form({"notation": notation}, fragment),
                )

    def test_does_not_treat_complete_internal_colon_forms_as_fragments(self) -> None:
        for notation, form in (
            ("BB:t; pl. BB:n", "BB:t"),
            ("+:n +:ar", ":n"),
            ("abc:na", "abc:na"),
        ):
            with self.subTest(notation=notation, form=form):
                self.assertEqual(
                    "review_required",
                    classify_form({"notation": notation}, form),
                )

    def test_classifies_damage_to_arbitrary_explicit_forms(self) -> None:
        cases = (
            (
                {
                    "lemma": "basform",
                    "added_forms": ["heltannanform"],
                    "change_reasons": {"heltannanform": "explicit"},
                },
                "annanform",
            ),
            (
                {
                    "lemma": "basform",
                    "added_forms": ["heltannanform"],
                    "change_reasons": {"heltannanform": "explicit"},
                },
                "heltannan",
            ),
            (
                {
                    "lemma": "basform",
                    "added_forms": ["heltannanform"],
                    "change_reasons": {"heltannanform": "explicit"},
                },
                "basformannanform",
            ),
        )
        for row, damaged in cases:
            with self.subTest(damaged=damaged):
                self.assertEqual(
                    "legacy_explicit_form_error",
                    classify_form(row, damaged),
                )

    def test_does_not_guess_explicit_damage_without_explicit_provenance(self) -> None:
        row = {
            "lemma": "basform",
            "added_forms": ["heltannanform"],
            "change_reasons": {"heltannanform": "append"},
        }
        for form in ("annanform", "heltannan", "basformannanform"):
            with self.subTest(form=form):
                self.assertEqual("review_required", classify_form(row, form))

    def test_does_not_use_a_global_metadata_word_list(self) -> None:
        self.assertEqual("review_required", classify_form({}, "ibl"))
        self.assertEqual(
            "review_required",
            classify_form({"notation": "+n señoror"}, "señoror"),
        )

    def test_does_not_infer_colon_fragments_without_matching_notation(self) -> None:
        self.assertEqual(
            "review_required",
            classify_form({"notation": "+n +ar"}, "n"),
        )

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
                {
                    "record_id": "4",
                    "lemma": "okänd",
                    "notation": "+n +ar",
                    "stycke": "okänd",
                    "semantic_removed_forms": ["mystisk"],
                    "added_forms": [],
                    "change_reasons": {},
                },
            ]
        )
        self.assertEqual(4, review["semantic_rows"])
        self.assertEqual(1, review["review_required_rows"])
        self.assertEqual(1, review["review_required_forms"])
        self.assertEqual("okänd", review["rows"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
