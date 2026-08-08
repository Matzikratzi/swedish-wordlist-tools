import unittest

from swedish_wordlist_tools.classify_next_noun_batch import (
    SALDO_COMPETING_DEFINITE_SINGULAR_ALLOMORPH,
    SALDO_COMPETING_DEFINITE_SINGULAR_GENDER,
    SALDO_S_PLURAL_DEFINITE_PARADIGM,
    UNCLASSIFIED,
    classify_batch_row,
)


class NextNounBatchTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
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

    def test_s_plural_family_across_notations(self):
        for notation in ("+n; pl. +s", "+n; pl. + H +s", "+en; pl. +s", "+en; pl. +ar H +s"):
            classification, _ = classify_batch_row(self.row(notation=notation))
            self.assertEqual(SALDO_S_PLURAL_DEFINITE_PARADIGM, classification)

    def test_simple_gender_swap_both_directions(self):
        classification, _ = classify_batch_row(self.row(
            lemma="bor", notation="+et",
            extra_from_saol=["boret", "borets"],
            missing_from_saol=["boren", "borens"],
        ))
        self.assertEqual(SALDO_COMPETING_DEFINITE_SINGULAR_GENDER, classification)

        classification, _ = classify_batch_row(self.row(
            lemma="tandem", notation="+en",
            extra_from_saol=["tandemen", "tandemens"],
            missing_from_saol=["tandemet", "tandemets"],
        ))
        self.assertEqual(SALDO_COMPETING_DEFINITE_SINGULAR_GENDER, classification)

    def test_definite_singular_allomorph_swap(self):
        classification, _ = classify_batch_row(self.row(
            lemma="resistor", notation="+en +er",
            extra_from_saol=["resistoren", "resistorens"],
            missing_from_saol=["resistorn", "resistorns"],
        ))
        self.assertEqual(SALDO_COMPETING_DEFINITE_SINGULAR_ALLOMORPH, classification)

    def test_partial_patterns_are_not_classified(self):
        classification, _ = classify_batch_row(self.row(
            extra_from_saol=["bagelsna"],
        ))
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
