from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import split_alternative_branches
from swedish_wordlist_tools.saol_row_interpreter import (
    _NOUN_LABELLED_SLOT_GRAMMAR,
    _assign_labelled_noun_slots_shared,
    _coalesce_noun_slot_labels,
)
from swedish_wordlist_tools.saol_slot_interpreter import assign_slots_with_grammar


class NounSharedSlotInterpreterTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_plural_label_selects_plural_slot(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(self._tokens("pl. +ar"))
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("pl_indef",), tuple(item.slot for item in assigned))

    def test_definite_plural_is_composed_from_two_labels(self) -> None:
        tokens = self._tokens("best. pl. +na")
        self.assertEqual(("best.", "pl.", "+na"), tokens)
        self.assertEqual(("best.pl.", "+na"), _coalesce_noun_slot_labels(tokens))

        assigned = assign_slots_with_grammar(
            _coalesce_noun_slot_labels(tokens),
            _NOUN_LABELLED_SLOT_GRAMMAR,
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("pl_def",), tuple(item.slot for item in assigned))

    def test_el_reuses_preceding_plural_slot(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(
            self._tokens("pl. +er el. +ar")
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("pl_indef", "pl_indef"), tuple(item.slot for item in assigned))
        self.assertIsNone(assigned[0].alternative_marker)
        self.assertEqual("el.", assigned[1].alternative_marker)

    def test_compact_labelled_plural_uses_shared_slots(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(self._tokens("+et; pl. +"))
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def", "pl_indef"), tuple(item.slot for item in assigned))

    def test_unlabelled_relative_sequence_is_not_migrated_yet(self) -> None:
        self.assertIsNone(
            _assign_labelled_noun_slots_shared(self._tokens("+en +ar"))
        )


if __name__ == "__main__":
    unittest.main()
