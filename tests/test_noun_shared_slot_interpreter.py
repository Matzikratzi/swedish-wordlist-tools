from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import split_alternative_branches
from swedish_wordlist_tools.saol_row_interpreter import _assign_labelled_noun_slots_shared


class NounSharedSlotInterpreterTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_labelled_plural_and_definite_plural_use_shared_slots(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(
            self._tokens("ankaret; pl. ankare el. ankaren, best. pl. ankarna")
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "pl_indef", "pl_indef", "pl_def"),
            tuple(item.slot for item in assigned),
        )
        self.assertEqual("el.", assigned[2].alternative_marker)

    def test_compact_labelled_plural_uses_shared_slots(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(
            self._tokens("+et; pl. +")
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def", "pl_indef"), tuple(item.slot for item in assigned))

    def test_unlabelled_relative_sequence_is_not_migrated_yet(self) -> None:
        self.assertIsNone(
            _assign_labelled_noun_slots_shared(self._tokens("+en +ar"))
        )


if __name__ == "__main__":
    unittest.main()
