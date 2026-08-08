import unittest

from swedish_wordlist_tools.triage_singular_scope_mismatches import (
    COMPETING_DEFINITE_SINGULAR,
    MULTIWORD_OR_TOKENIZATION,
    OTHER,
    VARIANT_ORTHOGRAPHY,
    classify,
)


class SingularScopeMismatchTriageTests(unittest.TestCase):
    def test_variant_or_orthography(self):
        category, _ = classify({
            "lemma": "arvejord",
            "missing_singular_relative": ["=arvjord", "=arvjorden"],
            "saldo_extra_relative": ["+ar", "+arna"],
        })
        self.assertEqual(VARIANT_ORTHOGRAPHY, category)

    def test_competing_definite_singular(self):
        category, _ = classify({
            "lemma": "glycin",
            "missing_singular_relative": ["+et", "+ets"],
            "saldo_extra_relative": ["+en", "+ens", "+er", "+erna", "+ernas", "+ers"],
        })
        self.assertEqual(COMPETING_DEFINITE_SINGULAR, category)

    def test_multiword(self):
        category, _ = classify({
            "lemma": "pommes frites",
            "missing_singular_relative": ["+en", "+ens"],
            "saldo_extra_relative": ["=pommes", "=frites"],
        })
        self.assertEqual(MULTIWORD_OR_TOKENIZATION, category)

    def test_other(self):
        category, _ = classify({
            "lemma": "busk",
            "missing_singular_relative": ["+s"],
            "saldo_extra_relative": ["+e", "+es", "+ar"],
        })
        self.assertEqual(OTHER, category)


if __name__ == "__main__":
    unittest.main()
