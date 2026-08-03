from __future__ import annotations

import unittest

from swedish_wordlist_tools.validate_row_interpreter_saldo import validation_row


class ValidateRowInterpreterSaldoTests(unittest.TestCase):
    def record(self, lemma: str, pattern: str, stycke: str = ""):
        return {
            "id": "1",
            "homonr": "2",
            "normaliserat_ord": lemma,
            "text": pattern,
            "stycke": stycke,
            "ordkl": "s.",
            "upos": "NOUN",
        }

    def analysis(self, *forms: str):
        return {
            "id": "test..nn.1",
            "upos": "NOUN",
            "lemmas": {forms[0]},
            "forms": set(forms),
        }

    def test_all_key_forms_exist_in_saldo(self) -> None:
        row = validation_row(
            self.record("hund", "+en +ar"),
            "lemma_same_upos",
            [self.analysis("hund", "hunden", "hundar")],
        )
        self.assertEqual("all_key_forms_in_saldo", row["status"])
        self.assertEqual([], row["missing_key_forms_from_saldo"])
        self.assertEqual("1", row["record_id"])
        self.assertEqual("2", row["homonym_number"])
        self.assertEqual("s.", row["ordkl"])

    def test_reports_missing_interpreted_key_form(self) -> None:
        row = validation_row(
            self.record("fiskelag", "+et; pl. +"),
            "lemma_same_upos",
            [self.analysis("fiskelag", "fiskelagen")],
        )
        self.assertEqual("some_key_forms_missing_from_saldo", row["status"])
        self.assertEqual(["fiskelaget"], row["missing_key_forms_from_saldo"])

    def test_uses_bar_marked_replacement(self) -> None:
        row = validation_row(
            self.record("alarmklocka", "+n -klockor", "alarm|klocka"),
            "lemma_same_upos",
            [self.analysis("alarmklocka", "alarmklockan", "alarmklockor")],
        )
        self.assertEqual("all_key_forms_in_saldo", row["status"])

    def test_validates_multiple_forms_in_same_slot(self) -> None:
        row = validation_row(
            self.record("fredag", "+en el. vard. -dan; pl. +ar", "fre|dag"),
            "lemma_same_upos",
            [self.analysis("fredag", "fredagen", "fredan", "fredagar")],
        )
        self.assertEqual("all_key_forms_in_saldo", row["status"])
        self.assertEqual(
            ["fredag", "fredagen", "fredan", "fredagar"],
            row["key_forms"],
        )


if __name__ == "__main__":
    unittest.main()
