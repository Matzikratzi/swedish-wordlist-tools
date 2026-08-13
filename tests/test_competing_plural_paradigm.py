import unittest

from swedish_wordlist_tools.classify_form_mismatches import (
    SALDO_COMPETING_PLURAL_PARADIGM,
    UNCLASSIFIED,
    classify_row,
)


class CompetingPluralParadigmTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "status": "form_set_mismatch",
            "upos": "NOUN",
            "lemma": "hajk",
            "homonym_number": "1",
            "notation": "+en +er",
            "extra_from_saol": ["hajker", "hajkers", "hajkerna", "hajkernas"],
            "missing_from_saol": ["hajkar", "hajkars", "hajkarna", "hajkarnas"],
        }
        row.update(overrides)
        return row

    def test_er_in_saol_ar_in_saldo(self):
        classification, rationale = classify_row(self.row())
        self.assertEqual(SALDO_COMPETING_PLURAL_PARADIGM, classification)
        self.assertIn("competing regular plural paradigm", rationale)

    def test_ar_in_saol_er_in_saldo(self):
        classification, _ = classify_row(
            self.row(
                notation="+en +ar",
                lemma="vurm",
                extra_from_saol=["vurmar", "vurmars", "vurmarna", "vurmarnas"],
                missing_from_saol=["vurmer", "vurmers", "vurmerna", "vurmersnas"],
            )
        )
        # Deliberately malformed SALDO genitive plural: exact-pattern guard must reject it.
        self.assertEqual(UNCLASSIFIED, classification)

    def test_ar_in_saol_er_in_saldo_exact(self):
        classification, rationale = classify_row(
            self.row(
                notation="+en +ar",
                lemma="vurm",
                extra_from_saol=["vurmar", "vurmars", "vurmarna", "vurmarnas"],
                missing_from_saol=["vurmer", "vurmers", "vurmerna", "vurmernas"],
            )
        )
        self.assertEqual(SALDO_COMPETING_PLURAL_PARADIGM, classification)
        self.assertIn("competing regular plural paradigm", rationale)

    def test_partial_difference_is_not_classified(self):
        classification, _ = classify_row(
            self.row(
                extra_from_saol=["hajker", "hajkerna"],
                missing_from_saol=["hajkar", "hajkarna"],
            )
        )
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
