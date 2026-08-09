import unittest

from swedish_wordlist_tools.noun_mechanical_validation import (
    is_mechanically_verified_noun_notation,
    is_mechanically_verified_noun_row,
    is_null_noun_notation,
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

    def test_structured_alternatives_are_verified_at_row_level(self):
        cases = (
            ("väsen", "+det; pl. +, best. pl. +dena _ +t +n [-en] +r [-er]"),
            ("fäbless", "+en +er _ +n [-en] +r [-er]"),
            ("citrat", "+et; pl. +er el. +"),
            ("alfa", "+t; pl. +n el. +"),
            ("kamratskap", "+et el. +en"),
            ("fredag", "+en el. vard. -dan; pl. +ar"),
        )
        for lemma, notation in cases:
            with self.subTest(notation=notation):
                self.assertTrue(
                    is_mechanically_verified_noun_row(
                        {
                            "lemma": lemma,
                            "notation": notation,
                            "stycke": lemma,
                        }
                    )
                )

    def test_structured_alternatives_are_not_global_string_allowlist(self):
        self.assertFalse(
            is_mechanically_verified_noun_notation(
                "+en +er _ +n [-en] +r [-er]"
            )
        )

    def test_truncated_or_prose_structured_rows_stay_unverified(self):
        truncated = "+n; pl. kamrar el. +, best. pl. kamrarna el. kamma"
        self.assertEqual(50, len(truncated))
        self.assertFalse(
            is_mechanically_verified_noun_row(
                {"lemma": "kammare", "notation": truncated, "stycke": "kammare"}
            )
        )
        self.assertFalse(
            is_mechanically_verified_noun_row(
                {
                    "lemma": "test",
                    "notation": "+en; som: pl. används: +er el. +ar",
                    "stycke": "test",
                }
            )
        )

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
                        {
                            "lemma": lemma,
                            "notation": "(null)",
                            "ordkl": ordkl,
                        }
                    )
                )

    def test_ordkl_is_not_used_when_text_contains_unhandled_notation(self):
        self.assertFalse(
            is_mechanically_verified_noun_row(
                {
                    "lemma": "test",
                    "notation": "+en; som: pl. används: +er el. +ar",
                    "ordkl": "s. oböjl.",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
