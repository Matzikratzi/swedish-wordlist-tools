import unittest

from swedish_wordlist_tools.classify_form_mismatches import (
    SALDO_COMPETING_GENDER_AND_FULL_PLURAL,
    UNCLASSIFIED,
    classify_row,
)


class CompetingGenderFullPluralIntegrationTests(unittest.TestCase):
    def row(self, *, missing):
        return {
            "status": "form_set_mismatch",
            "upos": "NOUN",
            "notation": "+et",
            "lemma": "duns",
            "extra_from_saol": ["dunset", "dunsets"],
            "missing_from_saol": missing,
        }

    def test_classifies_ar_plural(self):
        classification, _ = classify_row(
            self.row(
                missing=[
                    "dunsen",
                    "dunsens",
                    "dunsar",
                    "dunsars",
                    "dunsarna",
                    "dunsarnas",
                ]
            )
        )
        self.assertEqual(SALDO_COMPETING_GENDER_AND_FULL_PLURAL, classification)

    def test_classifies_er_plural(self):
        classification, _ = classify_row(
            self.row(
                missing=[
                    "dunsen",
                    "dunsens",
                    "dunser",
                    "dunsers",
                    "dunserna",
                    "dunsernas",
                ]
            )
        )
        self.assertEqual(SALDO_COMPETING_GENDER_AND_FULL_PLURAL, classification)

    def test_does_not_classify_partial_competing_paradigm(self):
        classification, _ = classify_row(
            self.row(missing=["dunsen", "dunsens", "dunsar", "dunsarna"])
        )
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
