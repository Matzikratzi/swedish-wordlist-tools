from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbSlotsTests(unittest.TestCase):
    def record(self, lemma: str, pattern: str):
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_interprets_regular_two_form_notation(self) -> None:
        slots = interpret_verb_slots(self.record("abonnera", "+de +t"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("abonnera",), slots.forms_for("infinitive"))
        self.assertEqual(("abonnerade",), slots.forms_for("preterite"))
        self.assertEqual(("abonnerat",), slots.forms_for("supine"))

    def test_inflects_before_reflexive_pronoun(self) -> None:
        slots = interpret_verb_slots(self.record("blamera sig", "+de +t"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("blamerade sig",), slots.forms_for("preterite"))
        self.assertEqual(("blamerat sig",), slots.forms_for("supine"))

    def test_interprets_explicit_irregular_forms(self) -> None:
        slots = interpret_verb_slots(self.record("gå", "går gick gått"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("går",), slots.forms_for("present"))
        self.assertEqual(("gick",), slots.forms_for("preterite"))
        self.assertEqual(("gått",), slots.forms_for("supine"))

    def test_rejects_other_word_classes_and_unknown_syntax(self) -> None:
        record = self.record("abonnera", "+de +t")
        record["upos"] = "NOUN"
        self.assertIsNone(interpret_verb_slots(record))
        self.assertIsNone(interpret_verb_slots(self.record("göra", "pres. gör")))


if __name__ == "__main__":
    unittest.main()
