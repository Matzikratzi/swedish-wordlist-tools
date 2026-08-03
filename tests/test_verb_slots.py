from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbSlotsTests(unittest.TestCase):
    def record(self, lemma: str, pattern: str, stycke: str = ""):
        return {
            "normaliserat_ord": lemma,
            "text": pattern,
            "stycke": stycke,
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

    def test_interprets_labelled_expanded_notation(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "sätta",
                "satte, satt, satt n. satt, pres. sätter",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("sätter",), slots.forms_for("present"))
        self.assertEqual(("satte",), slots.forms_for("preterite"))
        self.assertEqual(("satt",), slots.forms_for("supine"))

    def test_interprets_bar_marked_compound_forms(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "tillsätta",
                "-satte, -satt, -satt n. -satt, pres. -sätter",
                "till|sätta",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("tillsätter",), slots.forms_for("present"))
        self.assertEqual(("tillsatte",), slots.forms_for("preterite"))
        self.assertEqual(("tillsatt",), slots.forms_for("supine"))

    def test_keeps_colloquial_preterite_alternative(self) -> None:
        slots = interpret_verb_slots(
            self.record("lägga", "lade el. vard. la, lagt, lagd n. lagt, pres. lägger")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("lade", "la"), slots.forms_for("preterite"))
        self.assertEqual(("lagt",), slots.forms_for("supine"))
        self.assertEqual(("lägger",), slots.forms_for("present"))

    def test_rejects_other_word_classes_and_unknown_syntax(self) -> None:
        record = self.record("abonnera", "+de +t")
        record["upos"] = "NOUN"
        self.assertIsNone(interpret_verb_slots(record))
        self.assertIsNone(interpret_verb_slots(self.record("göra", "pres. gör")))


if __name__ == "__main__":
    unittest.main()
