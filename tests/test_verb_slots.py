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
            self.record("sätta", "satte, satt, satt n. satt, pres. sätter")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("sätter",), slots.forms_for("present"))
        self.assertEqual(("satte",), slots.forms_for("preterite"))
        self.assertEqual(("satt",), slots.forms_for("supine"))

    def test_ignores_participle_block(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "skriva",
                "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("skriver",), slots.forms_for("present"))
        self.assertEqual(("skrev",), slots.forms_for("preterite"))
        self.assertEqual(("skrivit",), slots.forms_for("supine"))
        self.assertNotIn("skriven", slots.written_forms())

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

    def test_interprets_bar_marked_participle_family(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "avskriva",
                "-skrev, -skrivit, -skriven -skrivet -skrivna; pres. -skriver",
                "av|skriva",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("avskriver",), slots.forms_for("present"))
        self.assertEqual(("avskrev",), slots.forms_for("preterite"))
        self.assertEqual(("avskrivit",), slots.forms_for("supine"))

    def test_finds_present_label_after_comment_punctuation(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "skriva",
                "skrev, skrivit, skriven skrivet skrivna: pres. skriver",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("skriver",), slots.forms_for("present"))

    def test_keeps_colloquial_preterite_alternative(self) -> None:
        slots = interpret_verb_slots(
            self.record("lägga", "lade el. vard. la, lagt, lagd n. lagt, pres. lägger")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("lade", "la"), slots.forms_for("preterite"))
        self.assertEqual(("lagt",), slots.forms_for("supine"))
        self.assertEqual(("lägger",), slots.forms_for("present"))

    def test_keeps_h_marked_alternatives(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "tvinga",
                "tvingade H tvang, tvingat H tvungit, tvingad n. tvingat, pres. tvingar",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("tvingade", "tvang"), slots.forms_for("preterite"))
        self.assertEqual(("tvingat", "tvungit"), slots.forms_for("supine"))

    def test_interprets_underscore_spelling_variants(self) -> None:
        slots = interpret_verb_slots(
            self.record("låtsas", "låtsades låtsats _ låssades låssats")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("låtsades", "låssades"), slots.forms_for("preterite"))
        self.assertEqual(("låtsats", "låssats"), slots.forms_for("supine"))

    def test_accepts_explicit_no_inflection(self) -> None:
        slots = interpret_verb_slots(self.record("månde", "ingen: böjning:"))
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("månde",), slots.forms_for("infinitive"))
        self.assertEqual(("månde",), slots.written_forms())

    def test_interprets_source_truncated_at_present_label(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "avskriva",
                "-skrev, -skrivit, -skriven -skrivet -skrivna, pres",
                "av|skriva",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("avskrev",), slots.forms_for("preterite"))
        self.assertEqual(("avskrivit",), slots.forms_for("supine"))
        self.assertEqual((), slots.forms_for("present"))

    def test_keeps_key_forms_when_present_form_is_truncated(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "artbestämma",
                "-bestämde, -bestämt, -bestämd n. -bestämt, pres. -",
                "art|bestämma",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("artbestämde",), slots.forms_for("preterite"))
        self.assertEqual(("artbestämt",), slots.forms_for("supine"))

    def test_interprets_two_comma_groups_without_present(self) -> None:
        slots = interpret_verb_slots(
            self.record("byta", "bytte el. prov. böt, bytt")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("bytte", "böt"), slots.forms_for("preterite"))
        self.assertEqual(("bytt",), slots.forms_for("supine"))

    def test_applies_bar_replacement_before_reflexive_pronoun(self) -> None:
        slots = interpret_verb_slots(
            self.record(
                "företa sig",
                "-tog, -tagit, -tagen -taget -tagna, pres. -tar",
                "före|ta",
            )
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("företar sig",), slots.forms_for("present"))
        self.assertEqual(("företog sig",), slots.forms_for("preterite"))
        self.assertEqual(("företagit sig",), slots.forms_for("supine"))

    def test_strips_parenthetical_comment_in_compact_notation(self) -> None:
        slots = interpret_verb_slots(
            self.record("ana", "+de el. (i: ett: uttryck:) ante, +t")
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("anade", "ante"), slots.forms_for("preterite"))
        self.assertEqual(("anat",), slots.forms_for("supine"))

    def test_rejects_other_word_classes_and_unknown_syntax(self) -> None:
        record = self.record("abonnera", "+de +t")
        record["upos"] = "NOUN"
        self.assertIsNone(interpret_verb_slots(record))
        self.assertIsNone(interpret_verb_slots(self.record("göra", "pres. gör")))


if __name__ == "__main__":
    unittest.main()
