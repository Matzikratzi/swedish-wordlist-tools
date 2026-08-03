from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_participles import (
    add_explicit_perfect_participles,
    explicit_perfect_participle_tokens,
)
from swedish_wordlist_tools.verb_slot_schema import add_explicit_verb_row_slots
from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbParticipleTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str = "") -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke or lemma,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_extracts_three_explicit_participle_tokens(self) -> None:
        record = self.record(
            "skriva",
            "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
        )
        self.assertEqual(
            ("skriven", "skrivet", "skrivna"),
            explicit_perfect_participle_tokens(record),
        )

        base = interpret_verb_slots(record)
        self.assertIsNotNone(base)
        assert base is not None
        slots = add_explicit_perfect_participles(record, base)
        self.assertEqual(("skriven",), slots.forms_for("perfect_participle_common"))
        self.assertEqual(("skrivet",), slots.forms_for("perfect_participle_neuter"))
        self.assertEqual(("skrivna",), slots.forms_for("perfect_participle_plural"))

    def test_applies_bar_marked_participles_to_compound(self) -> None:
        record = self.record(
            "avskriva",
            "-skrev, -skrivit, -skriven -skrivet -skrivna, pres. -skriver",
            "av|skriva",
        )
        base = interpret_verb_slots(record)
        self.assertIsNotNone(base)
        assert base is not None
        slots = add_explicit_verb_row_slots(record, base)
        self.assertEqual(("avskriven",), slots.forms_for("perfect_participle_common"))
        self.assertEqual(("avskrivet",), slots.forms_for("perfect_participle_neuter"))
        self.assertEqual(("avskrivna",), slots.forms_for("perfect_participle_plural"))
        self.assertEqual(("avskriver",), slots.forms_for("present_active"))

    def test_does_not_treat_short_comment_as_three_form_paradigm(self) -> None:
        record = self.record(
            "lägga",
            "lade, lagt, lagd n. lagt, pres. lägger",
        )
        self.assertIsNone(explicit_perfect_participle_tokens(record))
        base = interpret_verb_slots(record)
        self.assertIsNotNone(base)
        assert base is not None
        self.assertIs(base, add_explicit_perfect_participles(record, base))

    def test_does_not_extract_from_truncated_third_group(self) -> None:
        record = self.record(
            "avskriva",
            "-skrev, -skrivit, -skriven -skrivet -s, pres. -skr",
            "av|skriva",
        )
        self.assertIsNone(explicit_perfect_participle_tokens(record))


if __name__ == "__main__":
    unittest.main()
