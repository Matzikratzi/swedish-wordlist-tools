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

    def test_analogy_is_not_used_without_matching_parallel_structure(self) -> None:
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
        self.assertEqual("structural_positive_sequence", slots.rule)


if __name__ == "__main__":
    unittest.main()
