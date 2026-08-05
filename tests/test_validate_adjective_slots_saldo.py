from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_adjective_slots_saldo import validation_row


def generated(lemma: str, forms: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "record_id": "1",
        "lemma": lemma,
        "homonym_number": "1",
        "rule": "test",
        "source_notation": "+t +a",
        "effective_notation": "+t +a",
        "stycke": lemma,
        "forms": [
            {
                "written_form": written_form,
                "slot": slot,
                "provenance": "row",
                "source_token": "",
            }
            for written_form, slot in forms
        ],
    }


class ValidateAdjectiveSlotsSaldoTests(unittest.TestCase):
    def test_marks_all_pre_generated_slots_found_in_saldo(self) -> None:
        row = validation_row(
            generated("glad", [
                ("glad", "common_singular"),
                ("glatt", "neuter_singular"),
                ("glada", "definite_or_plural"),
            ]),
            "lemma",
            [{"forms": {"glad", "glatt", "glada"}}],
        )
        self.assertEqual("all_slot_forms_in_saldo", row["status"])
        self.assertEqual([], row["missing_forms"])
        self.assertEqual(
            {"common_singular", "neuter_singular", "definite_or_plural"},
            {form["slot"] for form in row["forms"]},
        )

    def test_reports_missing_pre_generated_form_with_its_slot(self) -> None:
        row = validation_row(
            generated("glad", [
                ("glad", "common_singular"),
                ("glatt", "neuter_singular"),
                ("glada", "definite_or_plural"),
            ]),
            "lemma",
            [{"forms": {"glad", "glada"}}],
        )
        self.assertEqual("some_slot_forms_missing_from_saldo", row["status"])
        self.assertEqual(
            [{
                "written_form": "glatt",
                "slot": "neuter_singular",
                "provenance": "row",
                "source_token": "",
                "in_saldo": False,
            }],
            row["missing_forms"],
        )

    def test_validator_preserves_generated_form_verbatim(self) -> None:
        row = validation_row(
            generated("förstfödd", [
                ("förstfödd", "common_singular"),
                ("förstfött", "neuter_singular"),
                ("förstfödda", "definite_or_plural"),
            ]),
            "lemma",
            [{"forms": {"förstfödd", "förstfödda"}}],
        )
        self.assertEqual(
            ["förstfödd", "förstfött", "förstfödda"],
            [form["written_form"] for form in row["forms"]],
        )
        self.assertEqual("förstfött", row["missing_forms"][0]["written_form"])


if __name__ == "__main__":
    unittest.main()
