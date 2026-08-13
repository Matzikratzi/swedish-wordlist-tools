import unittest

from swedish_wordlist_tools.classify_form_mismatches_batched import classify_rows


class BatchedMismatchClassifierTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "status": "form_set_mismatch",
            "paradigm_status": "form_set_mismatch",
            "upos": "NOUN",
            "notation": "+n; pl. +s",
            "lemma": "bagel",
            "homonym_number": "1",
            "extra_from_saol": ["bagelsna", "bagelsnas"],
            "missing_from_saol": ["bagelsen", "bagelsens", "bagelsarna", "bagelsarnas"],
        }
        row.update(overrides)
        return row

    def test_applies_verified_batch_to_base_unclassified_row(self):
        rows = classify_rows([self.row()])
        self.assertEqual(1, len(rows))
        self.assertEqual("saldo_s_plural_definite_paradigm", rows[0]["mismatch_classification"])

    def test_preserves_existing_base_classification(self):
        rows = classify_rows([
            self.row(
                notation="+en +er",
                lemma="abstinens",
                extra_from_saol=["abstinenser", "abstinensers", "abstinenserna", "abstinensernas"],
                missing_from_saol=[],
            )
        ])
        self.assertEqual("saldo_missing_plural", rows[0]["mismatch_classification"])


if __name__ == "__main__":
    unittest.main()
