from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_direct_forms_lexeme import validation_row


class RegularNounSubsetClassificationTests(unittest.TestCase):
    def test_classifies_clean_en_er_subset_as_source_difference(self) -> None:
        record = {
            "normaliserat_ord": "modell",
            "homonr": "1",
            "ordkl": "s. +en +er",
            "upos": "NOUN",
        }
        analyses = [{
            "id": "modell..nn.1",
            "lemmas": ["modell"],
            "forms": ["modell", "modellen", "modellens", "modells"],
            "upos": "NOUN",
        }]

        row = validation_row(record, "lemma_same_upos", analyses)

        self.assertEqual("saol_paradigm_differs_from_saldo", row["status"])
        self.assertEqual([], row["missing_from_saol"])

    def test_classifies_clean_en_ar_subset_as_source_difference(self) -> None:
        record = {
            "normaliserat_ord": "hund",
            "homonr": "1",
            "ordkl": "s. +en +ar",
            "upos": "NOUN",
        }
        analyses = [{
            "id": "hund..nn.1",
            "lemmas": ["hund"],
            "forms": ["hund", "hunden", "hundens", "hunds"],
            "upos": "NOUN",
        }]

        row = validation_row(record, "lemma_same_upos", analyses)

        self.assertEqual("saol_paradigm_differs_from_saldo", row["status"])
        self.assertEqual([], row["missing_from_saol"])

    def test_keeps_conflicting_saldo_forms_as_mismatch(self) -> None:
        record = {
            "normaliserat_ord": "hund",
            "homonr": "1",
            "ordkl": "s. +en +ar",
            "upos": "NOUN",
        }
        analyses = [{
            "id": "hund..nn.1",
            "lemmas": ["hund"],
            "forms": ["hund", "hunden", "hundens", "hunds", "hunder"],
            "upos": "NOUN",
        }]

        row = validation_row(record, "lemma_same_upos", analyses)

        self.assertEqual("form_set_mismatch", row["status"])
        self.assertIn("hunder", row["missing_from_saol"])


if __name__ == "__main__":
    unittest.main()
