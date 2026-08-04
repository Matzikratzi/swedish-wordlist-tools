from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbTruncatedCoreTests(unittest.TestCase):
    def record(self, lemma: str, text: str) -> dict[str, object]:
        self.assertEqual(50, len(text), text)
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": lemma,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_keeps_compact_core_before_semicolon_comment(self) -> None:
        text = "+de +t; perf. part. pl. +de el. i: ett: uttryck: l"
        slots = interpret_verb_slots(self.record("låna", text))

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("lånade",), slots.forms_for("preterite"))
        self.assertEqual(("lånat",), slots.forms_for("supine"))
        self.assertNotIn("l", slots.written_forms())

    def test_keeps_two_complete_groups_before_truncated_participle(self) -> None:
        text = "bringade el. bragte, bringat el. bragt, bringad el"
        slots = interpret_verb_slots(self.record("bringa", text))

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("bringade", "bragte"), slots.forms_for("preterite"))
        self.assertEqual(("bringat", "bragt"), slots.forms_for("supine"))
        self.assertNotIn("bringad", slots.written_forms())

    def test_keeps_three_complete_groups_before_truncated_participle(self) -> None:
        text = "förklär el. åld. förkläder, förklädde, förklätt, f"
        slots = interpret_verb_slots(self.record("förklä", text))

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("förklär", "förkläder"), slots.forms_for("present"))
        self.assertEqual(("förklädde",), slots.forms_for("preterite"))
        self.assertEqual(("förklätt",), slots.forms_for("supine"))
        self.assertNotIn("f", slots.written_forms())


if __name__ == "__main__":
    unittest.main()
