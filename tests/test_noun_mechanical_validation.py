import unittest

from swedish_wordlist_tools.noun_mechanical_validation import (
    is_mechanically_verified_noun_notation,
    is_mechanically_verified_noun_row,
    is_null_noun_notation,
)


class NounMechanicalValidationTests(unittest.TestCase):
    def test_regular_singular_only_and_zero_plural_allowlist(self):
        for notation in (
            "+en",
            "+et",
            "+n",
            "+t",
            "+en +er",
            "+et; pl. +",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_explicit_plural_replacement_is_mechanical(self):
        for notation in (
            "+n -syror",
            "+n -känslor",
            "+n -massor",
            "+n -soppor",
            "+n -oljor",
            "+n -vätskor",
            "+n -sidor",
            "+en -rötter",
            "+n -ändar",
            "+n; pl. -ändar",
            "+en; pl. -rötter",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_explicit_used_plural_is_mechanical(self):
        self.assertTrue(is_mechanically_verified_noun_notation("best. +; i: pl. används: -verkningar"))
        self.assertTrue(is_mechanically_verified_noun_notation("best. +; i: pl. används: -ansökningar"))

    def test_branching_or_compound_notation_stays_unverified_from_notation_alone(self):
        for notation in (
            "+n; pl. -kamrar el. +, best. pl. -kamrarna el. -ka",
            "+en +er _ +n [-en] +r [-er]",
            "+det; pl. +, best. pl. +dena _ +t +n",
            "+et; pl. +er el. +",
            "+t; pl. +n el. +",
        ):
            with self.subTest(notation=notation):
                self.assertFalse(is_mechanically_verified_noun_notation(notation))

    def test_materialized_two_lemma_underscore_branch_is_mechanical(self):
        row = {
            "lemma": "bankväsen",
            "notation": "+det; pl. +, best. pl. +dena _ +t +n",
            "variant_validation": [
                {
                    "lemma": "bankväsen",
                    "generated_forms": [
                        "bankväsen",
                        "bankväsens",
                        "bankväsendet",
                        "bankväsendena",
                    ],
                },
                {
                    "lemma": "bankväsende",
                    "generated_forms": [
                        "bankväsende",
                        "bankväsendes",
                        "bankväsendet",
                        "bankväsenden",
                    ],
                },
            ],
        }
        self.assertTrue(is_mechanically_verified_noun_row(row))

    def test_underscore_branch_without_materialized_variant_stays_diagnostic(self):
        row = {
            "lemma": "test",
            "notation": "+en +er _ +n +r",
            "variant_validation": [
                {"lemma": "test", "generated_forms": ["test", "testen", "tester"]}
            ],
        }
        self.assertFalse(is_mechanically_verified_noun_row(row))

    def test_missing_notation_representations(self):
        for value in (None, "", "(null)", "null", "  (NULL)  "):
            with self.subTest(value=value):
                self.assertTrue(is_null_noun_notation(value))
        self.assertFalse(is_null_noun_notation("+en"))

    def test_ordkl_carriers_are_mechanically_verified_through_interpreter(self):
        for lemma, ordkl in (
            ("alter ego", "s. oböjl."),
            ("kröken", "s. best."),
            ("fårakläder", "s. pl."),
        ):
            with self.subTest(ordkl=ordkl):
                self.assertTrue(
                    is_mechanically_verified_noun_row(
                        {"lemma": lemma, "notation": "(null)", "ordkl": ordkl}
                    )
                )

    def test_ordkl_is_not_used_when_text_contains_notation(self):
        self.assertFalse(
            is_mechanically_verified_noun_row(
                {"lemma": "test", "notation": "+t; pl. +n el. +", "ordkl": "s. oböjl."}
            )
        )


if __name__ == "__main__":
    unittest.main()
