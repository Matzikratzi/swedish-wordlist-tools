import unittest

from swedish_wordlist_tools.classify_competing_gender_plural import (
    SALDO_COMPETING_GENDER_AND_FULL_PLURAL,
    classify_competing_gender_plural,
)
from swedish_wordlist_tools.classify_form_mismatches import UNCLASSIFIED


class CompetingGenderPluralTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "status": "form_set_mismatch",
            "upos": "NOUN",
            "notation": "+et",
            "lemma": "duns",
            "extra_from_saol": ["dunset", "dunsets"],
            "missing_from_saol": [
                "dunsen",
                "dunsens",
                "dunsar",
                "dunsars",
                "dunsarna",
                "dunsarnas",
            ],
        }
        row.update(overrides)
        return row

    def test_classifies_et_vs_en_ar(self):
        classification, _ = classify_competing_gender_plural(self.row())
        self.assertEqual(SALDO_COMPETING_GENDER_AND_FULL_PLURAL, classification)

    def test_classifies_et_vs_en_er(self):
        classification, _ = classify_competing_gender_plural(
            self.row(
                lemma="glycin",
                extra_from_saol=["glycinet", "glycinets"],
                missing_from_saol=[
                    "glycinen",
                    "glycinens",
                    "glyciner",
                    "glyciners",
                    "glycinerna",
                    "glycinernas",
                ],
            )
        )
        self.assertEqual(SALDO_COMPETING_GENDER_AND_FULL_PLURAL, classification)

    def test_rejects_partial_plural(self):
        classification, _ = classify_competing_gender_plural(
            self.row(missing_from_saol=["dunsen", "dunsens", "dunsar", "dunsarna"])
        )
        self.assertEqual(UNCLASSIFIED, classification)

    def test_does_not_interpret_pl_plus(self):
        classification, _ = classify_competing_gender_plural(
            self.row(
                notation="pl. +",
                lemma="hertz",
                extra_from_saol=["hertzna", "hertznas"],
                missing_from_saol=["hertzen", "hertzens"],
            )
        )
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
