from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry
from swedish_wordlist_tools.validate_direct_forms_lexeme import validation_row


class NounSourceDifferenceTests(unittest.TestCase):
    def complete(self, lemma: str, notation: str):
        record = {
            "id": lemma,
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": notation,
        }
        return complete_noun_entry(record, generate_entry(record))

    def test_generates_both_singular_genders(self) -> None:
        entry = self.complete("kamratskap", "+et el. +en")
        self.assertIsNotNone(entry)
        self.assertEqual(
            {
                "kamratskap",
                "kamratskaps",
                "kamratskapet",
                "kamratskapets",
                "kamratskapen",
                "kamratskapens",
            },
            set(entry.forms if entry else ()),
        )

    def test_classifies_missing_neuter_definite(self) -> None:
        record = {
            "id": "abstinensbesvar",
            "normaliserat_ord": "abstinensbesvär",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+et; pl. +",
        }
        analysis = {
            "id": "abstinensbesvär..nn.1",
            "upos": "NOUN",
            "lemmas": {"abstinensbesvär"},
            "forms": {
                "abstinensbesvär",
                "abstinensbesvärs",
                "abstinensbesvären",
                "abstinensbesvärens",
            },
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("saol_neuter_definite_differs_from_saldo", row["status"])

    def test_classifies_zero_plural_against_ar_plural(self) -> None:
        record = {
            "id": "fiskelag",
            "normaliserat_ord": "fiskelag",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+et; pl. +",
        }
        analysis = {
            "id": "fiskelag..nn.1",
            "upos": "NOUN",
            "lemmas": {"fiskelag"},
            "forms": {
                "fiskelag", "fiskelags", "fiskelagen", "fiskelagens",
                "fiskelagar", "fiskelagarna", "fiskelagarnas", "fiskelagars",
            },
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("saol_zero_plural_differs_from_saldo", row["status"])

    def test_classifies_alternative_gender_missing_from_saldo(self) -> None:
        record = {
            "id": "kamratskap",
            "normaliserat_ord": "kamratskap",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+et el. +en",
        }
        analysis = {
            "id": "kamratskap..nn.1",
            "upos": "NOUN",
            "lemmas": {"kamratskap"},
            "forms": {"kamratskap", "kamratskaps", "kamratskapet", "kamratskapets"},
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("saol_alternative_gender_differs_from_saldo", row["status"])
        self.assertEqual(
            {"kamratskapen", "kamratskapens"},
            set(row["extra_from_saol"]),
        )


if __name__ == "__main__":
    unittest.main()
