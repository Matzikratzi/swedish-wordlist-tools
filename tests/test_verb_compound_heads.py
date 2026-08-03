from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_compound_heads import (
    borrow_compound_verb_slots,
    build_simple_verb_paradigm_index,
    compound_verb_parts,
)
from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class VerbCompoundHeadTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str) -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def test_extracts_exact_last_bar_head(self) -> None:
        record = self.record("återskriva", "", "åter|skriva")
        self.assertEqual(("åter", "skriva", ""), compound_verb_parts(record))

    def test_rejects_bar_markup_that_does_not_match_lemma(self) -> None:
        record = self.record("avresa", "", "<sup>1</sup>av|resa")
        record["normaliserat_ord"] = "avres"
        self.assertIsNone(compound_verb_parts(record))

    def test_borrows_missing_slots_from_independent_head_verb(self) -> None:
        base_record = self.record(
            "skriva",
            "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
            "skriva",
        )
        compound = self.record(
            "avskriva",
            "-skrev, -skrivit, -skriven -skrivet -skrivna, pres. -skr",
            "av|skriva",
        )
        base_slots = interpret_verb_slots(base_record)
        current = interpret_verb_slots(compound)
        self.assertIsNotNone(base_slots)
        self.assertIsNotNone(current)
        assert base_slots is not None
        index = build_simple_verb_paradigm_index(
            [base_record, compound],
            {id(base_record): base_slots, id(compound): current},
        )
        enriched = borrow_compound_verb_slots(compound, index, current)
        self.assertIsNotNone(enriched)
        assert enriched is not None
        self.assertEqual(("avskrev",), enriched.forms_for("preterite"))
        self.assertEqual(("avskrivit",), enriched.forms_for("supine"))
        self.assertEqual(("avskriver",), enriched.forms_for("present"))
        self.assertEqual("skriva", enriched.metadata["compound_head_source"])

    def test_keeps_existing_target_slot_instead_of_overwriting(self) -> None:
        base_record = self.record("skriva", "skriver skrev skrivit", "skriva")
        compound = self.record("avskriva", "avskriver avskrev avskrivit", "av|skriva")
        base_slots = interpret_verb_slots(base_record)
        current = interpret_verb_slots(compound)
        assert base_slots is not None and current is not None
        enriched = borrow_compound_verb_slots(compound, {"skriva": base_slots}, current)
        self.assertIs(enriched, current)

    def test_does_not_borrow_from_ambiguous_head_paradigms(self) -> None:
        first = self.record("giva", "gav givit", "giva")
        second = self.record("giva", "gav gett", "giva")
        first_slots = interpret_verb_slots(first)
        second_slots = interpret_verb_slots(second)
        assert first_slots is not None and second_slots is not None
        index = build_simple_verb_paradigm_index(
            [first, second],
            {id(first): first_slots, id(second): second_slots},
        )
        self.assertNotIn("giva", index)


if __name__ == "__main__":
    unittest.main()
