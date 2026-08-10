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

    def _assign(self, text: str):
        tokens = self._tokens(text)
        return assign_slots_with_grammar(
            _coalesce_noun_slot_labels(tokens),
            _NOUN_LABELLED_SLOT_GRAMMAR,
        )

    def test_each_primitive_operation_works_in_each_noun_slot(self) -> None:
        operations = {
            "+xy": 1,       # append
            "-xyz": 1,      # replace tail
            "+": 1,         # unchanged
            "helform": 1,   # explicit full form
            "+(e)n": 2,     # optional spelling => two realizations, same slot
        }
        slots = {
            "best. {token}": "sg_def",
            "pl. {token}": "pl_indef",
            "best. pl. {token}": "pl_def",
        }

        for token, expected_count in operations.items():
            for template, expected_slot in slots.items():
                text = template.format(token=token)
                with self.subTest(token=token, slot=expected_slot):
                    assigned = self._assign(text)
                    self.assertIsNotNone(assigned)
                    assert assigned is not None
                    self.assertEqual(expected_count, len(assigned))
                    self.assertEqual(
                        (expected_slot,) * expected_count,
                        tuple(item.slot for item in assigned),
                    )

    def test_each_alternative_marker_reuses_exactly_one_preceding_slot(self) -> None:
        for marker in ("el.", "H", "ibl."):
            for label, expected_slot in (
                ("best.", "sg_def"),
                ("pl.", "pl_indef"),
                ("best. pl.", "pl_def"),
            ):
                with self.subTest(marker=marker, slot=expected_slot):
                    assigned = self._assign(f"{label} +xy {marker} -xyz")
                    self.assertIsNotNone(assigned)
                    assert assigned is not None
                    self.assertEqual(
                        (expected_slot, expected_slot),
                        tuple(item.slot for item in assigned),
                    )
                    self.assertIsNone(assigned[0].alternative_marker)
                    self.assertEqual(marker.casefold(), assigned[1].alternative_marker)

    def test_definite_plural_is_only_a_composed_slot_label(self) -> None:
        tokens = self._tokens("best. pl. +xy")
        self.assertEqual(("best.", "pl.", "+xy"), tokens)
        self.assertEqual(("best.pl.", "+xy"), _coalesce_noun_slot_labels(tokens))

    def test_labelled_shared_wrapper_accepts_one_atomic_operation(self) -> None:
        for text, expected_slot in (
            ("pl. +xy", "pl_indef"),
            ("best. +xy", "sg_def"),
            ("best. pl. +xy", "pl_def"),
        ):
            with self.subTest(text=text):
                assigned = _assign_labelled_noun_slots_shared(self._tokens(text))
                self.assertIsNotNone(assigned)
                assert assigned is not None
                self.assertEqual((expected_slot,), tuple(item.slot for item in assigned))

    def test_unlabelled_sequence_is_not_part_of_this_contract(self) -> None:
        self.assertIsNone(
            _assign_labelled_noun_slots_shared(self._tokens("+en +ar"))
        )


if __name__ == "__main__":
    unittest.main()
