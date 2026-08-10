from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_row_interpreter import interpret_adjective_row


class AdjectiveRowInterpreterTests(unittest.TestCase):
    def parse(self, lemma: str, text: str):
        slots = interpret_adjective_row(
            {"normaliserat_ord": lemma, "text": text, "upos": "ADJ"}
        )
        self.assertIsNotNone(slots)
        return slots

    def test_unlabelled_positive_sequences_share_one_structural_rule(self) -> None:
        cases = (
            ("glad", "+t +a", ("glad", "glatt", "glada")),
            ("blå", "+tt +a", ("blå", "blått", "blåa")),
            ("öm", "+t +ma", ("öm", "ömt", "ömma")),
            ("bebodd", "bebott bebodda", ("bebodd", "bebott", "bebodda")),
            ("perenn", "perent +a", ("perenn", "perent", "perenna")),
            ("obunden", "-bundet -bundna", ("obunden", "obundet", "obundna")),
            ("osäker", "+t -säkra", ("osäker", "osäkert", "osäkra")),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_positive_sequence", slots.rule)

    def test_single_operations_are_assigned_by_operation_role(self) -> None:
        neuter = self.parse("dan", "+t")
        self.assertEqual(("dan", "dant"), neuter.written_forms())
        self.assertEqual("neuter_singular", neuter.forms[1].slot)

        explicit = self.parse("förstnämnde", "förstnämnda")
        self.assertEqual(("förstnämnde", "förstnämnda"), explicit.written_forms())
        self.assertEqual("definite_or_plural", explicit.forms[1].slot)

    def test_labels_and_parallel_branches_fall_back_without_output_change(self) -> None:
        labelled = self.parse("fullmäktig", "pl. +e")
        self.assertEqual(("fullmäktig", "fullmäktige"), labelled.written_forms())
        self.assertNotEqual("structural_positive_sequence", labelled.rule)

        parallel = self.parse("ledsen", "ledset ledsna _ lesset lessna")
        self.assertEqual(
            ("ledsen", "ledset", "ledsna", "lesset", "lessna"),
            parallel.written_forms(),
        )
        self.assertNotEqual("structural_positive_sequence", parallel.rule)


if __name__ == "__main__":
    unittest.main()
