from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import FormOperationKind
from swedish_wordlist_tools.saol_slot_interpreter import SlotGrammar, interpret_single_slot_sequence, interpret_slot_branches


def implicit_positive(index, last_slot, _operation):
    if index == 0:
        return "neuter"
    if last_slot == "neuter":
        return "plural"
    return None


class SaolSlotInterpreterTests(unittest.TestCase):
    def test_labels_and_alternatives(self) -> None:
        grammar = SlotGrammar(
            label_slots={"n.": "neuter", "pl.": "plural", "best.": "plural"},
            implicit_slot=implicit_positive,
            alternative_markers=frozenset({"el."}),
            transparent_markers=frozenset({"och:"}),
            require_marker=True,
        )
        operations = interpret_single_slot_sequence("-blått, best. och: pl. + el. +a", grammar)
        self.assertIsNotNone(operations)
        assert operations is not None
        self.assertEqual(("neuter", "plural", "plural"), tuple(item.slot for item in operations))
        self.assertEqual(
            (FormOperationKind.REPLACE_TAIL, FormOperationKind.UNCHANGED, FormOperationKind.APPEND),
            tuple(item.operation.kind for item in operations),
        )
        self.assertEqual("el.", operations[-1].alternative_marker)

    def test_relative_operations_are_notation_markers_themselves(self) -> None:
        grammar = SlotGrammar(
            label_slots={},
            implicit_slot=implicit_positive,
            require_marker=True,
        )
        operations = interpret_single_slot_sequence("+t +a", grammar)
        self.assertIsNotNone(operations)
        assert operations is not None
        self.assertEqual(("neuter", "plural"), tuple(item.slot for item in operations))

        # Plain explicit lexical forms have no structural marker on their own;
        # accepting those requires a word-class/source-context safety gate.
        self.assertIsNone(interpret_single_slot_sequence("neutrum plural", grammar))

    def test_independent_branches(self) -> None:
        grammar = SlotGrammar(label_slots={}, implicit_slot=implicit_positive)
        branches = interpret_slot_branches("fasetterat +e _ facetterat +e", grammar)
        self.assertIsNotNone(branches)
        assert branches is not None
        self.assertEqual(2, len(branches))
        self.assertEqual(
            (("neuter", "plural"), ("neuter", "plural")),
            tuple(tuple(item.slot for item in branch.operations) for branch in branches),
        )

    def test_unlicensed_label_is_rejected(self) -> None:
        grammar = SlotGrammar(label_slots={"pl.": "plural"}, implicit_slot=implicit_positive, require_marker=True)
        self.assertIsNone(interpret_single_slot_sequence("komp. +re", grammar))


if __name__ == "__main__":
    unittest.main()
