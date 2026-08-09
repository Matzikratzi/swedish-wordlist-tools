import unittest

from swedish_wordlist_tools.noun_mechanical_validation import (
    is_mechanically_verified_noun_notation,
)


class NounMechanicalValidationTests(unittest.TestCase):
    def test_regular_and_zero_plural_allowlist(self):
        self.assertTrue(is_mechanically_verified_noun_notation("+en +er"))
        self.assertTrue(is_mechanically_verified_noun_notation("+et; pl. +"))

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
        ):
            with self.subTest(notation=notation):
                self.assertTrue(is_mechanically_verified_noun_notation(notation))

    def test_explicit_used_plural_is_mechanical(self):
        self.assertTrue(
            is_mechanically_verified_noun_notation("best. +; i: pl. används: -verkningar")
        )
        self.assertTrue(
            is_mechanically_verified_noun_notation("best. +; i: pl. används: -ansökningar")
        )

    def test_branching_or_compound_notation_stays_unverified(self):
        for notation in (
            "+n; pl. -kamrar el. +, best. pl. -kamrarna el. -ka",
            "+en +er _ +n [-en] +r [-er]",
            "+et; pl. +er el. +",
            "+t; pl. +n el. +",
        ):
            with self.subTest(notation=notation):
                self.assertFalse(is_mechanically_verified_noun_notation(notation))


if __name__ == "__main__":
    unittest.main()
