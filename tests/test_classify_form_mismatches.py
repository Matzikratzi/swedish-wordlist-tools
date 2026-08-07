import unittest

from swedish_wordlist_tools.classify_form_mismatches import (
    SALDO_MISSING_DEFINITE_PLURAL,
    SALDO_MISSING_PLURAL,
    UNCLASSIFIED,
    build_summary,
    classify_row,
    classify_rows,
)


class ClassifyFormMismatchesTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "status": "form_set_mismatch",
            "upos": "NOUN",
            "notation": "+en +er",
            "lemma": "abstinens",
            "homonym_number": "1",
            "extra_from_saol": [
                "abstinenser",
                "abstinensers",
                "abstinenserna",
                "abstinensernas",
            ],
            "missing_from_saol": [],
        }
        row.update(overrides)
        return row

    def test_classifies_exact_missing_er_plural_paradigm(self):
        classification, rationale = classify_row(self.row())
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+en +er", rationale)

    def test_classifies_exact_missing_ar_plural_paradigm(self):
        classification, rationale = classify_row(
            self.row(
                notation="+en +ar",
                lemma="amning",
                extra_from_saol=["amningar", "amningars", "amningarna", "amningarnas"],
            )
        )
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+en +ar", rationale)

    def test_classifies_exact_missing_n_plural_paradigm(self):
        classification, rationale = classify_row(
            self.row(
                notation="+t +n",
                lemma="bemötande",
                extra_from_saol=["bemötanden", "bemötandens", "bemötandena", "bemötandenas"],
            )
        )
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+t +n", rationale)

    def test_classifies_exact_missing_r_plural_paradigm(self):
        classification, rationale = classify_row(
            self.row(
                notation="+n +r",
                lemma="beblandelse",
                extra_from_saol=[
                    "beblandelser",
                    "beblandelsers",
                    "beblandelserna",
                    "beblandelsernas",
                ],
            )
        )
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+n +r", rationale)

    def test_classifies_exact_missing_er_plural_for_n_er(self):
        classification, rationale = classify_row(
            self.row(
                notation="+n +er",
                lemma="nivå",
                extra_from_saol=["nivåer", "nivåers", "nivåerna", "nivåernas"],
            )
        )
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+n +er", rationale)

    def test_classifies_exact_missing_er_plural_for_et_er(self):
        classification, rationale = classify_row(
            self.row(
                notation="+et +er",
                lemma="garn",
                extra_from_saol=["garner", "garners", "garnerna", "garnernas"],
            )
        )
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+et +er", rationale)

    def test_classifies_missing_definite_zero_plural(self):
        classification, rationale = classify_row(
            self.row(
                notation="+et; pl. +",
                lemma="ansvar",
                extra_from_saol=["ansvaren", "ansvarens"],
            )
        )
        self.assertEqual(SALDO_MISSING_DEFINITE_PLURAL, classification)
        self.assertIn("definite plural", rationale)

    def test_classifies_missing_definite_zero_plural_na(self):
        classification, rationale = classify_row(
            self.row(
                notation="+en; pl. +",
                lemma="cent",
                extra_from_saol=["centna", "centnas"],
            )
        )
        self.assertEqual(SALDO_MISSING_DEFINITE_PLURAL, classification)
        self.assertIn("definite plural", rationale)

    def test_does_not_hide_competing_plural(self):
        classification, _ = classify_row(
            self.row(missing_from_saol=["abstinenserar"])
        )
        self.assertEqual(UNCLASSIFIED, classification)

    def test_does_not_accept_competing_singular_for_n_er(self):
        classification, _ = classify_row(
            self.row(
                notation="+n +er",
                lemma="autonomi",
                extra_from_saol=["autonomier", "autonomiers", "autonomierna", "autonomiernas"],
                missing_from_saol=["autonomien", "autonomiens"],
            )
        )
        self.assertEqual(UNCLASSIFIED, classification)

    def test_does_not_accept_partial_plural_difference(self):
        classification, _ = classify_row(
            self.row(extra_from_saol=["abstinenser", "abstinenserna"])
        )
        self.assertEqual(UNCLASSIFIED, classification)

    def test_summary_counts_classified_and_unclassified(self):
        rows = classify_rows(
            [
                self.row(),
                self.row(
                    lemma="hajk",
                    extra_from_saol=["hajker"],
                    missing_from_saol=["hajkar"],
                ),
            ]
        )
        summary = build_summary(rows)
        self.assertEqual(2, summary["mismatch_records"])
        self.assertEqual(1, summary["classified_records"])
        self.assertEqual(1, summary["unclassified_records"])
        self.assertEqual({"NOUN": 1}, summary["unclassified_upos_counts"])

    def test_summary_ranks_exact_unclassified_structures(self):
        rows = classify_rows(
            [
                self.row(
                    notation="+en +ar",
                    lemma="alpha",
                    extra_from_saol=["alphaar"],
                    missing_from_saol=["alphaer"],
                ),
                self.row(
                    notation="+en +ar",
                    lemma="beta",
                    extra_from_saol=["betaar"],
                    missing_from_saol=["betaer"],
                ),
                self.row(
                    notation="+et; pl. +",
                    lemma="gamma",
                    extra_from_saol=["gammaet"],
                    missing_from_saol=[],
                ),
            ]
        )
        groups = build_summary(rows)["unclassified_groups"]
        self.assertEqual(2, groups[0]["count"])
        self.assertEqual("+en +ar", groups[0]["notation"])
        self.assertEqual(["+ar"], groups[0]["extra_pattern"])
        self.assertEqual(["+er"], groups[0]["missing_pattern"])
        self.assertEqual(["alpha", "beta"], [item["lemma"] for item in groups[0]["examples"]])


if __name__ == "__main__":
    unittest.main()
