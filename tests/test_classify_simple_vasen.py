from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_next_noun_batch import (
    SALDO_SIMPLE_VASEN_DEFINITE_PLURAL_PARADIGM,
    classify_batch_row,
)
from swedish_wordlist_tools.classify_form_mismatches import UNCLASSIFIED


class SimpleVasenBatchTests(unittest.TestCase):
    def test_classifies_simple_vasen_definite_plural_conflict(self) -> None:
        row = {
            "upos": "NOUN",
            "lemma": "andeväsen",
            "notation": "+det; pl. +, best. pl. +dena",
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": ["andeväsendena", "andeväsendenas"],
            "missing_from_saol": ["andeväsena", "andeväsenas"],
        }
        classification, _ = classify_batch_row(row)
        self.assertEqual(SALDO_SIMPLE_VASEN_DEFINITE_PLURAL_PARADIGM, classification)

    def test_requires_exact_difference(self) -> None:
        row = {
            "upos": "NOUN",
            "lemma": "andeväsen",
            "notation": "+det; pl. +, best. pl. +dena",
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": ["andeväsendena"],
            "missing_from_saol": ["andeväsena", "andeväsenas"],
        }
        classification, _ = classify_batch_row(row)
        self.assertEqual(UNCLASSIFIED, classification)

    def test_requires_vasen_lemma(self) -> None:
        row = {
            "upos": "NOUN",
            "lemma": "exempel",
            "notation": "+det; pl. +, best. pl. +dena",
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": ["exempeldena", "exempeldenas"],
            "missing_from_saol": ["exempela", "exempelas"],
        }
        classification, _ = classify_batch_row(row)
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
