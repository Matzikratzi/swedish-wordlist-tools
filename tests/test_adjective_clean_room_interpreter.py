from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_clean_room_interpreter import interpret_adjective_row


class AdjectiveCleanRoomInterpreterTests(unittest.TestCase):
    def test_parallel_variant_lemma_is_inferred_by_branch_analogy(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "sjangdobel",
                "text": "+t sjangdobla _ +t schangdobla",
                "stycke": "sjangd·obel",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            (
                "sjangdobel",
                "sjangdobelt",
                "sjangdobla",
                "schangdobel",
                "schangdobelt",
                "schangdobla",
            ),
            slots.written_forms(),
        )
        self.assertEqual("structural_parallel_analogical_branches", slots.rule)

    def test_two_atom_positive_sequence_uses_shared_slots(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "glad",
                "text": "+t +a",
                "stycke": "glad",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("glad", "glatt", "glada"), slots.written_forms())
        self.assertEqual(
            ("common_singular", "neuter_singular", "definite_or_plural"),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_positive_atoms", slots.rule)

    def test_four_atom_sequence_uses_same_shared_slot_order(self) -> None:
        slots = interpret_adjective_row(
            {
                "normaliserat_ord": "stor",
                "text": "+t +a, större störst",
                "stycke": "stor",
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(
            ("stor", "stort", "stora", "större", "störst"),
            slots.written_forms(),
        )
        self.assertEqual(
            (
                "common_singular",
                "neuter_singular",
                "definite_or_plural",
                "comparative",
                "superlative",
            ),
            tuple(form.slot for form in slots.forms),
        )
        self.assertEqual("shared_full_adjective_atoms", slots.rule)


if __name__ == "__main__":
    unittest.main()
