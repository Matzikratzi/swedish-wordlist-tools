from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_direct_forms import select_direct_match, validation_row


class ValidateDirectFormsTests(unittest.TestCase):
    def test_selects_exact_lemma_with_same_upos(self) -> None:
        record = {"normaliserat_ord": "flicka", "upos": "NOUN", "ordkl": "subst."}
        analysis = {
            "id": "flicka..nn.1",
            "upos": "NOUN",
            "lemmas": {"flicka"},
            "forms": {"flicka", "flickan", "flickor"},
        }
        selected = select_direct_match(record, {"flicka": [analysis]}, {})
        self.assertIsNotNone(selected)
        method, analyses = selected or ("", [])
        self.assertEqual("lemma_same_upos", method)
        self.assertEqual([analysis], analyses)

    def test_reports_completed_noun_forms_as_subset(self) -> None:
        record = {
            "id": 1,
            "normaliserat_ord": "flicka",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+n +r",
        }
        analysis = {
            "id": "flicka..nn.1",
            "upos": "NOUN",
            "lemmas": {"flicka"},
            "forms": {
                "flicka", "flickas", "flickan", "flickans",
                "flickar", "flickars", "flickarna", "flickarnas",
                "flickor",
            },
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("saol_forms_are_subset", row["status"])
        self.assertEqual(["flickor"], row["missing_from_saol"])
        self.assertEqual([], row["extra_from_saol"])

    def test_reports_zero_plural_disagreement_separately(self) -> None:
        record = {
            "id": 2,
            "normaliserat_ord": "ansvar",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+et; pl. +",
        }
        analysis = {
            "id": "ansvar..nn.1",
            "upos": "NOUN",
            "lemmas": {"ansvar"},
            "forms": {"ansvar", "ansvars", "ansvaret", "ansvarets"},
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("saol_zero_plural_differs_from_saldo", row["status"])
        self.assertEqual(["ansvaren", "ansvarens"], row["extra_from_saol"])
        self.assertEqual(
            "saol_forms_are_subset->saol_zero_plural_differs_from_saldo",
            row["status_transition"],
        )

    def test_excludes_hyphen_terminated_saldo_forms(self) -> None:
        record = {
            "normaliserat_ord": "grund",
            "upos": "NOUN",
            "ordkl": "subst.",
            "text": "+en",
        }
        analysis = {
            "id": "grund..nn.1",
            "upos": "NOUN",
            "lemmas": {"grund"},
            "forms": {"grund", "grunden", "grund-"},
        }
        row = validation_row(record, "lemma_same_upos", [analysis])
        self.assertEqual("exact_form_set", row["status"])
        self.assertNotIn("grund-", row["saldo_forms"])


if __name__ == "__main__":
    unittest.main()
