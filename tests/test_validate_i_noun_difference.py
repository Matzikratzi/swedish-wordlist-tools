from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_direct_forms_lexeme import validation_row


class ValidateINounDifferenceTests(unittest.TestCase):
    def test_classifies_autonomi_as_modern_saol_paradigm(self) -> None:
        record = {
            "id": "autonomi-1",
            "normaliserat_ord": "autonomi",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+n +er",
        }
        analysis = {
            "id": "autonomi..nn.1",
            "upos": "NOUN",
            "lemmas": {"autonomi"},
            "forms": {
                "autonomi",
                "autonomis",
                "autonomin",
                "autonomins",
                "autonomien",
                "autonomiens",
            },
        }

        row = validation_row(record, "lemma_same_upos", [analysis])

        self.assertEqual(
            "saol_modern_definite_and_plural_differs_from_saldo",
            row["status"],
        )
        self.assertEqual(
            {"autonomier", "autonomiers", "autonomierna", "autonomiernas"},
            set(row["extra_from_saol"]),
        )
        self.assertEqual(
            {"autonomien", "autonomiens"},
            set(row["missing_from_saol"]),
        )

    def test_does_not_classify_hajk_noun_verb_conflict(self) -> None:
        record = {
            "id": "hajk-1",
            "normaliserat_ord": "hajk",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+en +er",
        }
        analysis = {
            "id": "hajk..nn.1",
            "upos": "NOUN",
            "lemmas": {"hajk"},
            "forms": {
                "hajk", "hajks", "hajken", "hajkens",
                "hajkar", "hajkars", "hajkarna", "hajkarnas",
            },
        }

        row = validation_row(record, "lemma_same_upos", [analysis])

        self.assertEqual("form_set_mismatch", row["status"])

    def test_requires_exact_old_definite_forms(self) -> None:
        record = {
            "id": "autonomi-1",
            "normaliserat_ord": "autonomi",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+n +er",
        }
        analysis = {
            "id": "autonomi..nn.1",
            "upos": "NOUN",
            "lemmas": {"autonomi"},
            "forms": {"autonomi", "autonomis", "autonomiar"},
        }

        row = validation_row(record, "lemma_same_upos", [analysis])

        self.assertEqual("form_set_mismatch", row["status"])


if __name__ == "__main__":
    unittest.main()
