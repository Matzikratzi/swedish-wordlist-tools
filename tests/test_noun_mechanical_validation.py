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

    def test_explicit_written_slot_forms_are_generic(self):
        for notation in (
            "+n askor",
            "+n auror",
            "+n blastulor",
            "+n bråtar",
            "+n canastor",
            "+en böter",
            "+en; pl. takfötter el. +ar",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_ibl_marks_fully_valid_alternative(self):
        for notation in (
            "+n; pl. + ibl. -metrar",
            "+n; pl. + ibl. -kilometrar",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_constrained_lexical_replacement_paradigms_are_mechanical(self):
        for notation in (
            "+en el. vard. -dan; pl. +ar",
            "-centret; pl. +, best. pl. -centren",
            "-öknen -öknar",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_explicit_used_plural_is_mechanical(self):
        self.assertTrue(is_mechanically_verified_noun_notation("best. +; i: pl. används: -verkningar"))
        self.assertTrue(is_mechanically_verified_noun_notation("best. +; i: pl. används: -ansökningar"))

    def test_fully_relative_el_alternatives_are_mechanical(self):
        for notation in (
            "+et el. +en",
            "+en el. +et",
            "+et; pl. +er el. +",
            "+t; pl. +n el. +",
            "+en; pl. +ar el. +er",
            "+et el. +en; pl. +",
            "+et el. +en; pl. + el. +er",
            "+et; pl. + el. +er",
            "+n el. +t; pl. +",
            "+en el. +et; pl. +ar el. +",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_fully_relative_h_alternatives_are_mechanical(self):
        for notation in (
            "+n; pl. + H +s",
            "+en; pl. +ar H +s",
            "+en; pl. +er H +s",
            "+et H +en",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_fully_relative_underscore_branches_are_mechanical(self):
        for notation in (
            "+det; pl. +, best. pl. +dena _ +t +n",
            "+en +er _ +n [-en] +r [-er]",
            "+en +er _ +n +er",
            "+en +er _ +n +r",
            "+en _ +n [-en]",
            "+et; pl. + _ +t +n",
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_unbounded_lexical_branching_stays_diagnostic(self):
        for notation in (
            "+n; pl. -kamrar el. +, best. pl. -kamrarna el. -ka",
            "+en _ ankaret",
            "+en _ -rötter",
            "+n; pl. + H gamlaformer",
        ):
            with self.subTest(notation=notation):
                self.assertFalse(is_mechanically_verified_noun_notation(notation))

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

    def test_ordkl_is_not_used_when_text_contains_unverified_notation(self):
        self.assertFalse(
            is_mechanically_verified_noun_row(
                {"lemma": "test", "notation": "+n; pl. + H gamlaformer", "ordkl": "s. oböjl."}
            )
        )


if __name__ == "__main__":
    unittest.main()
