import unittest

from swedish_wordlist_tools.classify_form_mismatches import (
    SALDO_VASEN_EXTRA_DEFINITE_SINGULAR_MISSING_DEFINITE_PLURAL,
    UNCLASSIFIED,
    classify_row,
)


class ClassifyVasenParadigmTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "status": "form_set_mismatch",
            "upos": "NOUN",
            "notation": "+det; pl. +, best. pl. +dena _ +t +n",
            "lemma": "tullväsen",
            "extra_from_saol": [
                "tullväsende",
                "tullväsenden",
                "tullväsendena",
                "tullväsendenas",
                "tullväsendens",
                "tullväsendes",
            ],
            "missing_from_saol": ["tullväsenet", "tullväsenets"],
            "variant_validation": [
                {
                    "lemma": "tullväsen",
                    "heading_type": "primary",
                    "status": "form_set_mismatch",
                    "extra_from_saol": ["tullväsendena", "tullväsendenas"],
                    "missing_from_saol": ["tullväsenet", "tullväsenets"],
                },
                {
                    "lemma": "tullväsende",
                    "heading_type": "alternative",
                    "status": "variant_missing_in_saldo",
                    "extra_from_saol": [
                        "tullväsende",
                        "tullväsenden",
                        "tullväsendena",
                        "tullväsendenas",
                        "tullväsendens",
                        "tullväsendes",
                    ],
                    "missing_from_saol": [],
                },
            ],
        }
        row.update(overrides)
        return row

    def test_classifies_exact_vasen_primary_difference(self):
        classification, rationale = classify_row(self.row())
        self.assertEqual(
            SALDO_VASEN_EXTRA_DEFINITE_SINGULAR_MISSING_DEFINITE_PLURAL,
            classification,
        )
        self.assertIn("-väsenet", rationale)
        self.assertIn("coverage difference", rationale)

    def test_requires_alternative_to_be_missing_in_saldo(self):
        row = self.row()
        row["variant_validation"][1]["status"] = "exact_form_set"
        classification, _ = classify_row(row)
        self.assertEqual(UNCLASSIFIED, classification)

    def test_does_not_accept_partial_primary_difference(self):
        row = self.row()
        row["variant_validation"][0]["extra_from_saol"] = ["tullväsendena"]
        classification, _ = classify_row(row)
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
