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

    def test_rejects_plausible_final_token_at_source_limit(self) -> None:
        # The final token is deliberately long and plausible. It is still
        # untrusted because the group reaches the 50-character source limit
        # without a following delimiter.
        text = "-skrev, -skrivit, -skriven -skrivet -skrivn"
        text = text.ljust(50, "x")[:50]
        record = self.record("avskriva", text, "av|skriva")
        self.assertEqual(50, len(text))
        self.assertIsNone(explicit_perfect_participle_tokens(record))

    def test_accepts_group_delimited_before_end_of_capped_row(self) -> None:
        # A later comma and present label prove that the complete third group
        # ended before the cap; the row may be truncated only after that point.
        text = "skrev, skrivit, skriven skrivet skrivna, pres. sju"
        self.assertEqual(50, len(text))
        record = self.record("skriva", text)
        self.assertEqual(
            ("skriven", "skrivet", "skrivna"),
            explicit_perfect_participle_tokens(record),
        )

    def test_participles_do_not_keep_reflexive_pronoun(self) -> None:
        record = self.record(
            "företa sig",
            "-tog, -tagit, -tagen -taget -tagna, pres. -tar",
            "före|ta",
        )
        base = interpret_verb_slots(record)
        self.assertIsNotNone(base)
        assert base is not None
        slots = add_explicit_perfect_participles(record, base)
        self.assertEqual(("företagen",), slots.forms_for("perfect_participle_common"))
        self.assertEqual(("företaget",), slots.forms_for("perfect_participle_neuter"))
        self.assertEqual(("företagna",), slots.forms_for("perfect_participle_plural"))

    def test_participles_do_not_keep_following_particles(self) -> None:
        record = self.record(
            "dra ihop sig",
            "drog, dragit, dragen draget dragna, pres. drar",
        )
        base = interpret_verb_slots(record)
        self.assertIsNotNone(base)
        assert base is not None
        slots = add_explicit_perfect_participles(record, base)
        self.assertEqual(("dragen",), slots.forms_for("perfect_participle_common"))
        self.assertEqual(("draget",), slots.forms_for("perfect_participle_neuter"))
        self.assertEqual(("dragna",), slots.forms_for("perfect_participle_plural"))


if __name__ == "__main__":
    unittest.main()
