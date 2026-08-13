from __future__ import annotations

import unittest

from swedish_wordlist_tools.lexeme_slots import SlotForm, build_lexeme_slots
from swedish_wordlist_tools.noun_slots import interpret_noun_slots


class LexemeSlotsTests(unittest.TestCase):
    def test_preserves_alternatives_in_same_slot(self) -> None:
        slots = build_lexeme_slots(
            lemma="fredag",
            upos="NOUN",
            notation="+en el. vard. -dan; pl. +ar",
            forms=(
                SlotForm("lemma", "fredag", "lemma"),
                SlotForm("sg_def", "fredagen", "+en"),
                SlotForm("sg_def", "fredan", "-dan"),
                SlotForm("pl_indef", "fredagar", "+ar"),
            ),
        )
        self.assertEqual(("fredagen", "fredan"), slots.forms_for("sg_def"))
        self.assertEqual("fredagen", slots.first("sg_def"))
        self.assertEqual(("lemma", "sg_def", "pl_indef"), slots.slots())

    def test_deduplicates_by_slot_and_spelling(self) -> None:
        slots = build_lexeme_slots(
            lemma="fiskelag",
            upos="noun",
            notation="+et; pl. +",
            forms=(
                SlotForm("sg_def", "fiskelaget", "+et"),
                SlotForm("pl_indef", "fiskelag", "+"),
                SlotForm("pl_indef", "fiskelag", "+"),
            ),
        )
        self.assertEqual("NOUN", slots.upos)
        self.assertEqual(("fiskelag", "fiskelaget"), slots.written_forms())
        self.assertEqual(("fiskelag",), slots.forms_for("pl_indef"))

    def test_adapts_noun_interpreter_without_losing_metadata(self) -> None:
        record = {
            "id": "123",
            "homonr": "1",
            "normaliserat_ord": "alarmklocka",
            "stycke": "a·larm|klocka",
            "ordkl": "s.",
            "text": "+n -klockor",
            "upos": "NOUN",
        }
        slots = interpret_noun_slots(record)
        self.assertIsNotNone(slots)
        self.assertEqual("alarmklockan", slots.first("sg_def") if slots else None)
        self.assertEqual(("alarmklockor",), slots.forms_for("pl_indef") if slots else ())
        self.assertEqual("123", slots.metadata.get("record_id") if slots else None)
        self.assertEqual("a·larm|klocka", slots.metadata.get("stycke") if slots else None)


if __name__ == "__main__":
    unittest.main()
