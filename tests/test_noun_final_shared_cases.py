from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import split_alternative_branches
from swedish_wordlist_tools.saol_row_interpreter import (
    _assign_labelled_noun_slots_shared,
    _assign_unlabelled_noun_atoms_shared,
    interpret_noun_row,
)


class NounFinalSharedCasesTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_arbitrary_colon_metadata_is_transparent_to_unlabelled_noun_gate(self) -> None:
        assigned = _assign_unlabelled_noun_atoms_shared(
            {"ordkl": "s."},
            self._tokens("+et el. i: vissa: uttryck: vard. spat"),
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def", "sg_def"), tuple(item.slot for item in assigned))
        self.assertEqual("el.", assigned[1].alternative_marker)

    def test_f_is_editorial_part_of_bestamd_form_label(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(self._tokens("best. f. +"))
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def",), tuple(item.slot for item in assigned))

    def test_spad_matches_saol_surface_forms(self) -> None:
        interpreted = interpret_noun_row(
            {
                "upos": "NOUN",
                "normaliserat_ord": "spad",
                "ordkl": "s. +et el. i: vissa: uttryck: vard. spat",
                "text": "+et el. i: vissa: uttryck: vard. spat",
                "stycke": "spad",
            }
        )
        self.assertIsNotNone(interpreted)
        assert interpreted is not None
        self.assertEqual(
            {"spad", "spadet", "spat"},
            {form.written_form for form in interpreted.key_forms},
        )

    def test_narkotikapaverkan_bestamd_form_is_unchanged(self) -> None:
        interpreted = interpret_noun_row(
            {
                "upos": "NOUN",
                "normaliserat_ord": "narkotikapåverkan",
                "ordkl": "s. best. f. +",
                "text": "best. f. +",
                "stycke": "narkotika|påverk·an",
            }
        )
        self.assertIsNotNone(interpreted)
        assert interpreted is not None
        self.assertEqual("narkotikapåverkan", interpreted.form("sg_def"))


if __name__ == "__main__":
    unittest.main()
