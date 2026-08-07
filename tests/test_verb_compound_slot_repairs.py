from __future__ import annotations

import unittest

from swedish_wordlist_tools.lexeme_slots import SlotForm, build_lexeme_slots
from swedish_wordlist_tools.verb_compound_heads import borrow_compound_verb_slots
from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbCompoundSlotRepairTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str) -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def source_slots(self) -> object:
        return build_lexeme_slots(
            lemma="skriva",
            upos="VERB",
            notation="test",
            forms=(
                SlotForm("present", "skriver", "test"),
                SlotForm("preterite", "skrev", "test"),
                SlotForm("supine", "skrivit", "test"),
            ),
        )

    def test_repairs_truncated_preterite(self) -> None:
        text = "-skr, -skrivit, pres. -skriver".ljust(50)
        record = self.record("avskriva", text, "av|skriva")
        current = interpret_verb_slots(record)
        self.assertIsNotNone(current)

        enriched = borrow_compound_verb_slots(
            record,
            {"skriva": self.source_slots()},
            current,
        )
        self.assertIsNotNone(enriched)
        assert enriched is not None
        self.assertEqual(("avskrev",), enriched.forms_for("preterite"))
        self.assertEqual(("avskrivit",), enriched.forms_for("supine"))

    def test_repairs_truncated_supine(self) -> None:
        text = "-skrev, -skr, pres. -skriver".ljust(50)
        record = self.record("avskriva", text, "av|skriva")
        current = interpret_verb_slots(record)
        self.assertIsNotNone(current)

        enriched = borrow_compound_verb_slots(
            record,
            {"skriva": self.source_slots()},
            current,
        )
        self.assertIsNotNone(enriched)
        assert enriched is not None
        self.assertEqual(("avskrev",), enriched.forms_for("preterite"))
        self.assertEqual(("avskrivit",), enriched.forms_for("supine"))


if __name__ == "__main__":
    unittest.main()
