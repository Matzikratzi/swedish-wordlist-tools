from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_adjective_slots_saldo import validation_row


class ValidateAdjectiveSlotsSaldoTests(unittest.TestCase):
    def test_marks_all_generated_slots_found_in_saldo(self) -> None:
        row = validation_row(
            {"normaliserat_ord": "glad", "text": "+t +a", "upos": "ADJ"},
            "lemma",
            [{"forms": {"glad", "glatt", "glada"}}],
        )
        self.assertEqual("all_slot_forms_in_saldo", row["status"])
        self.assertEqual([], row["missing_forms"])
        self.assertEqual(
            {"common_singular", "neuter_singular", "definite_or_plural"},
            {form["slot"] for form in row["forms"]},
        )

    def test_reports_missing_form_with_its_slot(self) -> None:
        row = validation_row(
            {"normaliserat_ord": "glad", "text": "+t +a", "upos": "ADJ"},
            "lemma",
            [{"forms": {"glad", "glada"}}],
        )
        self.assertEqual("some_slot_forms_missing_from_saldo", row["status"])
        self.assertEqual(
            [{"written_form": "glatt", "slot": "neuter_singular", "in_saldo": False}],
            row["missing_forms"],
        )

    def test_missing_saldo_form_does_not_change_saol_output(self) -> None:
        row = validation_row(
            {"normaliserat_ord": "beige", "text": "mest: oböjl., best. och: pl. ibl. beigea", "upos": "ADJ"},
            "lemma",
            [{"forms": {"beige"}}],
        )
        self.assertEqual("some_slot_forms_missing_from_saldo", row["status"])
        self.assertEqual(
            ["beige", "beigea"],
            [form["written_form"] for form in row["forms"]],
        )


if __name__ == "__main__":
    unittest.main()
