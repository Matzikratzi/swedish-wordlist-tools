from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import split_alternative_branches
from swedish_wordlist_tools.saol_row_interpreter import (
    _NOUN_LABELLED_SLOT_GRAMMAR,
    _assign_labelled_noun_slots_shared,
    _assign_unlabelled_noun_atoms_shared,
    _coalesce_noun_slot_labels,
    _explicit_branch_bases,
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
            "+xy": 1,
            "-xyz": 1,
            "+": 1,
            "helform": 1,
            "+(e)n": 2,
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

    def test_unlabelled_alternatives_reuse_same_slot_for_each_operation_kind(self) -> None:
        record = {"ordkl": "s."}
        for first, second in (
            ("+xy", "+ab"),
            ("+xy", "-xyz"),
            ("-xyz", "+xy"),
            ("+xy", "+"),
            ("+xy", "helform"),
            ("helform", "+xy"),
        ):
            with self.subTest(first=first, second=second):
                assigned = _assign_unlabelled_noun_atoms_shared(
                    record,
                    self._tokens(f"{first} el. {second}"),
                )
                self.assertIsNotNone(assigned)
                assert assigned is not None
                self.assertEqual(
                    ("sg_def", "sg_def"),
                    tuple(item.slot for item in assigned),
                )
                self.assertEqual("el.", assigned[1].alternative_marker)

    def test_each_editorial_token_is_independently_transparent(self) -> None:
        cases = (
            ("i: pl. +xy", "pl_indef"),
            ("som: pl. +xy", "pl_indef"),
            ("pl. används: +xy", "pl_indef"),
            ("pl. anv. +xy", "pl_indef"),
            ("pl. kan: +xy", "pl_indef"),
            ("pl. användas: +xy", "pl_indef"),
            ("pl. vard. +xy", "pl_indef"),
        )
        for text, expected_slot in cases:
            with self.subTest(text=text):
                assigned = self._assign(text)
                self.assertIsNotNone(assigned)
                assert assigned is not None
                self.assertEqual((expected_slot,), tuple(item.slot for item in assigned))

    def test_vard_is_transparent_between_alternative_marker_and_form(self) -> None:
        assigned = _assign_labelled_noun_slots_shared(
            self._tokens("+en el. vard. -dan; pl. +ar")
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "sg_def", "pl_indef"),
            tuple(item.slot for item in assigned),
        )
        self.assertEqual("el.", assigned[1].alternative_marker)

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

    def test_unlabelled_atoms_compose_without_kind_specific_rule(self) -> None:
        record = {"ordkl": "s."}
        for text in (
            "+xy -xyz",
            "+xy helform",
            "helform +xy",
            "+xy +",
        ):
            with self.subTest(text=text):
                assigned = _assign_unlabelled_noun_atoms_shared(record, self._tokens(text))
                self.assertIsNotNone(assigned)
                assert assigned is not None
                self.assertEqual(
                    ("sg_def", "pl_indef"),
                    tuple(item.slot for item in assigned),
                )

    def test_optional_expansion_stays_in_first_implicit_slot(self) -> None:
        assigned = _assign_unlabelled_noun_atoms_shared(
            {"ordkl": "s."},
            self._tokens("+(e)n"),
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "sg_def"),
            tuple(item.slot for item in assigned),
        )

    def test_explicit_atom_requires_noun_context(self) -> None:
        assigned = _assign_unlabelled_noun_atoms_shared(
            {"ordkl": "s. helformen"},
            self._tokens("helformen"),
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def",), tuple(item.slot for item in assigned))

        self.assertIsNone(
            _assign_unlabelled_noun_atoms_shared(
                {"ordkl": "adj. helformen"},
                self._tokens("helformen"),
            )
        )

    def test_relative_atoms_do_not_require_noun_context(self) -> None:
        assigned = _assign_unlabelled_noun_atoms_shared(
            {},
            self._tokens("+en +ar"),
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(("sg_def", "pl_indef"), tuple(item.slot for item in assigned))

    def test_labelled_contract_does_not_claim_unlabelled_sequence(self) -> None:
        self.assertIsNone(
            _assign_labelled_noun_slots_shared(self._tokens("+en +ar"))
        )

    def test_underscore_only_splits_independent_branches(self) -> None:
        branches = split_alternative_branches("+xy _ -xyz")
        self.assertEqual(2, len(branches))
        self.assertEqual(("+xy",), branches[0].tokens)
        self.assertEqual(("-xyz",), branches[1].tokens)

    def test_each_underscore_branch_restarts_implicit_slot_sequence(self) -> None:
        branches = split_alternative_branches("+xy +ab _ -xyz +cd")
        self.assertEqual(2, len(branches))
        assigned = [
            _assign_unlabelled_noun_atoms_shared({}, branch.tokens)
            for branch in branches
        ]
        self.assertTrue(all(items is not None for items in assigned))
        self.assertEqual(
            [("sg_def", "pl_indef"), ("sg_def", "pl_indef")],
            [tuple(item.slot for item in items or ()) for items in assigned],
        )

    def test_explicit_variant_evidence_only_selects_branch_bases(self) -> None:
        record = {"_saol_alternative_lemma": "variant"}
        self.assertEqual(
            ("huvud", "variant"),
            _explicit_branch_bases(record, "huvud", 2),
        )
        self.assertEqual(
            ("huvud",),
            _explicit_branch_bases(record, "huvud", 1),
        )
        self.assertEqual(
            ("huvud", "huvud"),
            _explicit_branch_bases({}, "huvud", 2),
        )


if __name__ == "__main__":
    unittest.main()