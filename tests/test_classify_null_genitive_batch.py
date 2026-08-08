from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_form_mismatches import UNCLASSIFIED
from swedish_wordlist_tools.classify_null_genitive_batch import (
    SALDO_MISSING_BARE_GENITIVE_S,
    classify_null_genitive_row,
)


class NullGenitiveBatchTests(unittest.TestCase):
    def test_classifies_exact_bare_genitive_s_difference(self) -> None:
        row = {
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "gråben",
            "notation": "(null)",
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": ["gråbens"],
            "missing_from_saol": [],
        }
        classification, _ = classify_null_genitive_row(row)
        self.assertEqual(SALDO_MISSING_BARE_GENITIVE_S, classification)

    def test_rejects_other_missing_forms(self) -> None:
        row = {
            "mismatch_classification": "unclassified",
            "upos": "NOUN",
            "lemma": "gråben",
            "notation": "(null)",
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": ["gråbens"],
            "missing_from_saol": ["gråbenet"],
        }
        classification, _ = classify_null_genitive_row(row)
        self.assertEqual(UNCLASSIFIED, classification)


if __name__ == "__main__":
    unittest.main()
