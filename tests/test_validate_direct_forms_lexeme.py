from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_direct_forms_lexeme import validation_row


class ValidateDirectFormsLexemeTests(unittest.TestCase):
    def test_classifies_unique_form_match_to_other_lexeme(self) -> None:
        record = {
            "id": 1,
            "normaliserat_ord": "fälle",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+t +n",
        }
        analysis = {
            "id": "fälla..nn.1",
            "upos": "NOUN",
            "lemmas": {"fälla"},
            "forms": {
                "fälle", "fäll", "fälla", "fällan", "fällans", "fällas",
                "fällor", "fällorna", "fällornas", "fällors", "fälls",
            },
        }
        row = validation_row(record, "unique_form_same_upos", [analysis])
        self.assertEqual("saldo_form_match_other_lexeme", row["status"])
        self.assertEqual(
            "form_set_mismatch->saldo_form_match_other_lexeme",
            row["status_transition"],
        )

    def test_keeps_same_lemma_mismatch_unchanged(self) -> None:
        record = {
            "id": 2,
            "normaliserat_ord": "exempel",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+t +n",
        }
        analysis = {
            "id": "exempel..nn.1",
            "upos": "NOUN",
            "lemmas": {"exempel"},
            "forms": {"exempel", "exempels", "exemplen"},
        }
        row = validation_row(record, "unique_form_same_upos", [analysis])
        self.assertEqual("form_set_mismatch", row["status"])

    def test_keeps_non_form_match_mismatch_unchanged(self) -> None:
        record = {
            "id": 3,
            "normaliserat_ord": "fälle",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+t +n",
        }
        analysis = {
            "id": "fälla..nn.1",
            "upos": "NOUN",
            "lemmas": {"fälla"},
            "forms": {"fälle", "fälla"},
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("form_set_mismatch", row["status"])


if __name__ == "__main__":
    unittest.main()
