from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_shared_lexeme import interpret_shared_playable_verb_slots


class VerbSharedLexemeTests(unittest.TestCase):
    def parse(self, lemma: str, text: str | None):
        slots = interpret_shared_playable_verb_slots(
            {"normaliserat_ord": lemma, "upos": "VERB", "text": text, "stycke": lemma}
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        return slots

    def test_regular_relative_operations_are_realized(self) -> None:
        slots = self.parse("abonnera", "+de +t")
        self.assertEqual(("abonnera", "abonnerade", "abonnerat"), slots.written_forms())
        self.assertEqual(("abonnerade",), slots.forms_for("preterite"))
        self.assertEqual(("abonnerat",), slots.forms_for("supine"))

    def test_strong_explicit_forms_keep_their_slots(self) -> None:
        slots = self.parse("binda", "band, bundit, bunden bundet bundna, pres. binder")
        self.assertEqual(("band",), slots.forms_for("preterite"))
        self.assertEqual(("bundit",), slots.forms_for("supine"))
        self.assertEqual(("binder",), slots.forms_for("present"))
        self.assertEqual(("bunden",), slots.forms_for("perfect_participle_common"))
        self.assertEqual(("bundet",), slots.forms_for("perfect_participle_neuter"))
        self.assertEqual(("bundna",), slots.forms_for("perfect_participle_plural"))

    def test_49_character_ta_row_does_not_complete_missing_tail(self) -> None:
        text = "tog, tagit, tagen taget tagna, pres. tar el. åld."
        self.assertEqual(49, len(text))
        slots = self.parse("ta", text)
        self.assertEqual("true", slots.metadata["source_truncated"])
        self.assertEqual(("tar",), slots.forms_for("present"))
        self.assertNotIn("tager", slots.written_forms())
        self.assertNotIn("imperative", slots.slots())

    def test_missing_text_contributes_only_lemma(self) -> None:
        slots = self.parse("förbaske", None)
        self.assertEqual(("förbaske",), slots.written_forms())


if __name__ == "__main__":
    unittest.main()
