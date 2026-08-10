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

    def test_labelled_plural_tokenization_and_coalescing(self) -> None:
        # Keep the synthetic syntax test below SAOL14's known 50-character
        # source-text cap.  A text of exactly 50 characters intentionally drops
        # its final token as untrusted source data before tokenization.
        tokens = self._tokens("karet; pl. kar el. karen, best. pl. karen")
        self.assertEqual(
            ("karet", ";", "pl.", "kar", "el.", "karen", ",", "best.", "pl.", "karen"),
            tokens,
        )
        self.assertEqual(
            ("karet", ";", "pl.", "kar", "el.", "karen", ",", "best.pl.", "karen"),
            _coalesce_noun_slot_labels(tokens),
        )

    def test_coalesced_sequence_is_accepted_by_shared_engine(self) -> None:
        tokens = self._tokens("karet; pl. kar el. karen, best. pl. karen")
        assigned = assign_slots_with_grammar(
            _coalesce_noun_slot_labels(tokens),
            _NOUN_LABELLED_SLOT_GRAMMAR,
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "pl_indef", "pl_indef", "pl_def"),
            tuple(item.slot for item in assigned),
        )

    def test_labelled_plural_and_definite_plural_use_shared_slots(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(
            self._tokens("karet; pl. kar el. karen, best. pl. karen")
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "pl_indef", "pl_indef", "pl_def"),
            tuple(item.slot for item in assigned),
        )
        self.assertEqual("el.", assigned[2].alternative_marker)

    def test_exact_source_limit_drops_untrusted_final_token(self) -> None:
        text = "ankaret; pl. ankare el. ankaren, best. pl. ankarna"
        self.assertEqual(50, len(text))
        self.assertEqual(
            ("ankaret", ";", "pl.", "ankare", "el.", "ankaren", ",", "best.", "pl."),
            self._tokens(text),
        )

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
