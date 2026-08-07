import unittest

from swedish_wordlist_tools.classify_form_mismatches import (
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

    def test_classifies_exact_missing_plural_paradigm(self):
        classification, rationale = classify_row(self.row())
        self.assertEqual(SALDO_MISSING_PLURAL, classification)
        self.assertIn("+en +er", rationale)

    def test_does_not_hide_competing_plural(self):
        classification, _ = classify_row(
            self.row(missing_from_saol=["abstinenserar"])
        )
        self.assertEqual(UNCLASSIFIED, classification)

    def test_does_not_generalise_to_other_notation(self):
        classification, _ = classify_row(self.row(notation="+en +ar"))
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
