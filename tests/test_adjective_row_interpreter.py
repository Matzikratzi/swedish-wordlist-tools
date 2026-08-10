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

    def test_positive_labels_select_slots_structurally(self) -> None:
        cases = (
            ("kortväxt", "n. +, +a", ("kortväxt", "kortväxta")),
            ("hot", "neutr. +; pl. hotta", ("hot", "hotta")),
            ("fullmäktig", "pl. +e", ("fullmäktig", "fullmäktige")),
            ("främsta", "mask. främste", ("främsta", "främste")),
            (
                "akvamarinblå",
                "-blått, best. och: pl. + el. +a",
                ("akvamarinblå", "akvamarinblått", "akvamarinblåa"),
            ),
            (
                "blå",
                "blått, best. och: pl. blå el. blåa",
                ("blå", "blått", "blåa"),
            ),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_labelled_positive_slots", slots.rule)

    def test_positive_parallel_branches_are_independent(self) -> None:
        cases = (
            (
                "fasetterad",
                "fasetterat +e _ facetterat +e",
                (
                    "fasetterad",
                    "fasetterat",
                    "fasetterade",
                    "facetterad",
                    "facetterat",
                    "facetterade",
                ),
            ),
            (
                "hårdflörtad",
                "-flörtat +e _ -flirtat +e",
                (
                    "hårdflörtad",
                    "hårdflörtat",
                    "hårdflörtade",
                    "hårdflirtad",
                    "hårdflirtat",
                    "hårdflirtade",
                ),
            ),
            (
                "ledsen",
                "ledset ledsna _ lesset lessna",
                ("ledsen", "ledset", "ledsna", "lesset", "lessna"),
            ),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_parallel_positive_branches", slots.rule)

    def test_more_exotic_parallel_variant_still_falls_back(self) -> None:
        slots = self.parse("sjangdobel", "+t sjangdobla _ +t schangdobla")
        self.assertEqual(
            (
                "sjangdobel",
                "sjangdobelt",
                "sjangdobla",
                "schangdobel",
                "schangdobelt",
                "schangdobla",
            ),
            slots.written_forms(),
        )
        self.assertNotEqual("structural_parallel_positive_branches", slots.rule)

    def test_comparison_still_falls_back(self) -> None:
        comparison = self.parse("ringa", "komp. +re, superl. +st")
        self.assertEqual(("ringa", "ringare", "ringast"), comparison.written_forms())
        self.assertNotEqual("structural_labelled_positive_slots", comparison.rule)


if __name__ == "__main__":
    unittest.main()
