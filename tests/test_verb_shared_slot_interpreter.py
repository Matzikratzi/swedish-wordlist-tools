from __future__ import annotations

import unittest

from swedish_wordlist_tools.verb_shared_slot_interpreter import interpret_basic_verb_sequence


class VerbSharedSlotInterpreterTests(unittest.TestCase):
    def _pairs(self, text: str):
        assigned = interpret_basic_verb_sequence(text)
        self.assertIsNotNone(assigned)
        return tuple((item.slot, item.token, item.operation.kind.value) for item in assigned)

    def test_relative_suffix_atoms_fill_preterite_and_supine(self) -> None:
        self.assertEqual(
            (
                ("preterite", "+de", "append"),
                ("supine", "+t", "append"),
            ),
            self._pairs("+de +t"),
        )

    def test_full_written_atoms_use_the_same_slots(self) -> None:
        self.assertEqual(
            (
                ("preterite", "andades", "explicit"),
                ("supine", "andats", "explicit"),
            ),
            self._pairs("andades andats"),
        )

    def test_replacement_atoms_use_the_same_slots(self) -> None:
        self.assertEqual(
            (
                ("preterite", "-ställde", "replace_tail"),
                ("supine", "-ställt", "replace_tail"),
            ),
            self._pairs("-ställde -ställt"),
        )

    def test_longer_sequence_is_not_claimed_by_basic_interpreter(self) -> None:
        self.assertIsNone(interpret_basic_verb_sequence("gick gått pres. går"))


if __name__ == "__main__":
    unittest.main()
