from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slot_schema import add_precise_active_verb_slots
from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbSlotSchemaTests(unittest.TestCase):
    def record(self, lemma: str, text: str) -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": lemma,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_adds_precise_active_aliases_without_removing_legacy_slots(self) -> None:
        legacy = interpret_verb_slots(
            self.record(
                "skriva",
                "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
            )
        )
        self.assertIsNotNone(legacy)
        assert legacy is not None

        slots = add_precise_active_verb_slots(legacy)
        self.assertEqual(("skriva",), slots.forms_for("infinitive"))
        self.assertEqual(("skriva",), slots.forms_for("infinitive_active"))
        self.assertEqual(("skriver",), slots.forms_for("present"))
        self.assertEqual(("skriver",), slots.forms_for("present_active"))
        self.assertEqual(("skrev",), slots.forms_for("preterite_active"))
        self.assertEqual(("skrivit",), slots.forms_for("supine_active"))

    def test_only_adds_slots_that_exist_on_the_row(self) -> None:
        legacy = interpret_verb_slots(self.record("abonnera", "+de +t"))
        self.assertIsNotNone(legacy)
        assert legacy is not None

        slots = add_precise_active_verb_slots(legacy)
        self.assertEqual(("abonnera",), slots.forms_for("infinitive_active"))
        self.assertEqual(("abonnerade",), slots.forms_for("preterite_active"))
        self.assertEqual(("abonnerat",), slots.forms_for("supine_active"))
        self.assertEqual((), slots.forms_for("present_active"))

    def test_is_idempotent(self) -> None:
        legacy = interpret_verb_slots(self.record("gå", "går gick gått"))
        self.assertIsNotNone(legacy)
        assert legacy is not None

        once = add_precise_active_verb_slots(legacy)
        twice = add_precise_active_verb_slots(once)
        self.assertEqual(once.forms, twice.forms)

    def test_does_not_change_other_word_classes(self) -> None:
        legacy = interpret_verb_slots(self.record("gå", "går gick gått"))
        self.assertIsNotNone(legacy)
        assert legacy is not None
        object.__setattr__(legacy, "upos", "NOUN")
        self.assertIs(legacy, add_precise_active_verb_slots(legacy))


if __name__ == "__main__":
    unittest.main()
