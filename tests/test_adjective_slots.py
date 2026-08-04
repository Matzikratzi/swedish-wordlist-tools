from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_slots import interpret_simple_adjective_slots


class AdjectiveSlotsTests(unittest.TestCase):
    def parse(self, lemma: str, text: str):
        slots = interpret_simple_adjective_slots({
            "normaliserat_ord": lemma,
            "text": text,
            "upos": "ADJ",
        })
        self.assertIsNotNone(slots)
        return slots

    def test_regular_t_a_applies_neuter_spelling(self) -> None:
        slots = self.parse("glad", "+t +a")
        self.assertEqual(("glad", "glatt", "glada"), slots.written_forms())
        self.assertEqual("regular_t_a", slots.rule)

    def test_final_rd_and_ld_drop_d_before_t(self) -> None:
        self.assertEqual(
            ("hård", "hårt", "hårda"),
            self.parse("hård", "+t +a").written_forms(),
        )
        self.assertEqual(
            ("vild", "vilt", "vilda"),
            self.parse("vild", "+t +a").written_forms(),
        )

    def test_other_final_d_becomes_tt(self) -> None:
        self.assertEqual(
            ("röd", "rött", "röda"),
            self.parse("röd", "+t +a").written_forms(),
        )

    def test_unchanged_neuter(self) -> None:
        slots = self.parse("gratis", "n. +, +a")
        self.assertEqual(("gratis", "gratis", "gratisa"), slots.written_forms())
        self.assertEqual("unchanged_neuter_a", slots.rule)

    def test_regular_tt_a(self) -> None:
        slots = self.parse("blå", "+tt +a")
        self.assertEqual(("blå", "blått", "blåa"), slots.written_forms())

    def test_regular_t_ma(self) -> None:
        slots = self.parse("öm", "+t +ma")
        self.assertEqual(("öm", "ömt", "ömma"), slots.written_forms())

    def test_rejects_unhandled_pattern(self) -> None:
        self.assertIsNone(interpret_simple_adjective_slots({
            "normaliserat_ord": "bunden",
            "text": "-bundet -bundna",
        }))


if __name__ == "__main__":
    unittest.main()
