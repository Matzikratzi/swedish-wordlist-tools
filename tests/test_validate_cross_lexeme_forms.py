from __future__ import annotations

import unittest

import swedish_wordlist_tools.validate_direct_forms_lexeme as lexeme
from swedish_wordlist_tools.validate_direct_forms_lexeme import validation_row


class ValidateCrossLexemeFormsTests(unittest.TestCase):
    def test_classifies_noun_forms_explained_by_related_verb(self) -> None:
        record = {
            "id": "hajk-noun",
            "homonr": "1",
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
        old_entries = lexeme._SAOL_ENTRIES
        lexeme._SAOL_ENTRIES = [
            {
                "record_id": "hajka-verb",
                "homonym_number": "1",
                "lemma": "hajka",
                "lemma_key": "hajka",
                "upos": "VERB",
                "notation": "-r -de -t",
                "forms": {
                    "hajka", "hajkar", "hajkade", "hajkat",
                    "hajkars", "hajkarna", "hajkarnas",
                },
            }
        ]
        try:
            row = validation_row(record, "lemma_same_upos", [analysis])
        finally:
            lexeme._SAOL_ENTRIES = old_entries

        self.assertEqual(
            "saldo_forms_explained_by_other_saol_lexeme",
            row["status"],
        )
        self.assertEqual(
            [{
                "record_id": "hajka-verb",
                "homonym_number": "1",
                "lemma": "hajka",
                "upos": "VERB",
                "notation": "-r -de -t",
            }],
            row["explaining_saol_lexemes"],
        )

    def test_does_not_classify_single_coincidental_form(self) -> None:
        record = {
            "id": "test-noun",
            "normaliserat_ord": "test",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+en",
        }
        analysis = {
            "id": "test..nn.1",
            "upos": "NOUN",
            "lemmas": {"test"},
            "forms": {"test", "tests", "testen", "testens", "testar"},
        }
        old_entries = lexeme._SAOL_ENTRIES
        lexeme._SAOL_ENTRIES = [
            {
                "record_id": "testa-verb",
                "homonym_number": "1",
                "lemma": "testa",
                "lemma_key": "testa",
                "upos": "VERB",
                "notation": "-r -de -t",
                "forms": {"testa", "testar", "testade", "testat"},
            }
        ]
        try:
            row = validation_row(record, "lemma_same_upos", [analysis])
        finally:
            lexeme._SAOL_ENTRIES = old_entries

        self.assertEqual("form_set_mismatch", row["status"])


if __name__ == "__main__":
    unittest.main()
