import unittest

from swedish_wordlist_tools.integrate_next_noun_batch import integrate_rows


class IntegrateNextNounBatchTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "mismatch_classification": "unclassified",
            "status": "form_set_mismatch",
            "paradigm_status": "form_set_mismatch",
            "upos": "NOUN",
            "lemma": "bagel",
            "notation": "+n; pl. +s",
            "extra_from_saol": ["bagelsna", "bagelsnas"],
            "missing_from_saol": ["bagelsen", "bagelsens", "bagelsarna", "bagelsarnas"],
        }
        row.update(overrides)
        return row

    def test_integrates_s_plural_family(self):
        rows, changed = integrate_rows([self.row()])
        self.assertEqual(1, changed)
        self.assertEqual("saldo_s_plural_definite_paradigm", rows[0]["mismatch_classification"])

    def test_integrates_gender_swap(self):
        rows, changed = integrate_rows([
            self.row(
                lemma="bor",
                notation="+et",
                extra_from_saol=["boret", "borets"],
                missing_from_saol=["boren", "borens"],
            )
        ])
        self.assertEqual(1, changed)
        self.assertEqual("saldo_competing_definite_singular_gender", rows[0]["mismatch_classification"])

    def test_preserves_existing_classification(self):
        rows, changed = integrate_rows([
            self.row(mismatch_classification="saldo_missing_plural")
        ])
        self.assertEqual(0, changed)
        self.assertEqual("saldo_missing_plural", rows[0]["mismatch_classification"])


if __name__ == "__main__":
    unittest.main()
