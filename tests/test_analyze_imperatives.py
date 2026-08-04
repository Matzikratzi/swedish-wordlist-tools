from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_imperatives import (
    explicit_saol_imperatives,
    generate_imperative,
)
from swedish_wordlist_tools.lexeme_slots import SlotForm, build_lexeme_slots


class AnalyzeImperativesTests(unittest.TestCase):
    def slots(self, lemma: str, preterite: str):
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation="",
            forms=(SlotForm("preterite", preterite, "test"),),
        )

    def test_class1_keeps_infinitive(self) -> None:
        self.assertEqual(
            ("tala", "class1_preterite_ade"),
            generate_imperative("tala", self.slots("tala", "talade")),
        )

    def test_other_a_verb_drops_final_a(self) -> None:
        self.assertEqual(
            ("skriv", "drop_final_a"),
            generate_imperative("skriva", self.slots("skriva", "skrev")),
        )

    def test_non_a_infinitive_is_unchanged(self) -> None:
        self.assertEqual(("gå", "non_a_infinitive"), generate_imperative("gå", None))

    def test_extracts_complete_explicit_imperative(self) -> None:
        record = {
            "normaliserat_ord": "skriva",
            "text": "skrev, skrivit, pres. skriver, imper. skriv",
        }
        self.assertEqual(("skriv",), explicit_saol_imperatives(record))

    def test_drops_explicit_imperative_fragment_at_hard_cap(self) -> None:
        text = "skrev, skrivit, pres. skriver, imper. sk".ljust(50, "r")
        self.assertEqual(50, len(text))
        record = {"normaliserat_ord": "skriva", "text": text}
        self.assertEqual((), explicit_saol_imperatives(record))


if __name__ == "__main__":
    unittest.main()
