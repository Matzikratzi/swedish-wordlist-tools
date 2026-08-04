from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbTextHardCapTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str = "") -> dict[str, object]:
        self.assertEqual(50, len(text), text)
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_drops_truncated_present_but_keeps_earlier_forms(self) -> None:
        text = "sjöng, sjungit, sjungen sjunget sjungna, pres. sju"
        slots = interpret_verb_slots(self.record("sjunga", text))

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("sjöng",), slots.forms_for("preterite"))
        self.assertEqual(("sjungit",), slots.forms_for("supine"))
        self.assertEqual((), slots.forms_for("present"))
        self.assertNotIn("sju", slots.written_forms())
        self.assertEqual("true", slots.metadata["text_hard_cap"])

    def test_drops_long_plausible_fragment_at_hard_cap(self) -> None:
        text = "-föll, -fallit, -fallen -fallet -fallna, pres. -fa"
        slots = interpret_verb_slots(
            self.record("anfalla", text, "an|falla")
        )

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("anföll",), slots.forms_for("preterite"))
        self.assertEqual(("anfallit",), slots.forms_for("supine"))
        self.assertEqual((), slots.forms_for("present"))
        self.assertNotIn("anfa", slots.written_forms())

    def test_drops_final_supine_fragment_in_unlabelled_notation(self) -> None:
        text = "abcdefghijklmnopqrstuvwxade, abcdefghijklmnopqrst"
        slots = interpret_verb_slots(self.record("abcdefghijklmnopqrstuvwa", text))

        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("abcdefghijklmnopqrstuvwxade",),
            slots.forms_for("preterite"),
        )
        self.assertEqual((), slots.forms_for("supine"))
        self.assertNotIn("abcdefghijklmnopqrst", slots.written_forms())


if __name__ == "__main__":
    unittest.main()
