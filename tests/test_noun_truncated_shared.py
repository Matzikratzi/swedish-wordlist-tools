from __future__ import annotations

import unittest

from swedish_wordlist_tools.noun_truncated_shared import (
    assign_truncated_noun_branch,
    interpret_truncated_noun_row,
)
from swedish_wordlist_tools.saol_notation import split_alternative_branches


class NounTruncatedSharedTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_recovers_only_complete_prefix_before_unfinished_slot(self) -> None:
        assigned = assign_truncated_noun_branch(
            {"ordkl": "s."},
            self._tokens("+en; pl. +ar, best. pl."),
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            ("sg_def", "pl_indef"),
            tuple(item.slot for item in assigned),
        )

    def test_interpreted_row_does_not_invent_missing_definite_plural(self) -> None:
        row = interpret_truncated_noun_row(
            {
                "normaliserat_ord": "test",
                "upos": "NOUN",
                "ordkl": "s.",
                "text": "+en; pl. +ar, best. pl.",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(
            (("lemma", "test"), ("sg_def", "testen"), ("pl_indef", "testar")),
            tuple((form.slot, form.written_form) for form in row.key_forms),
        )

    def test_truncated_branch_with_no_complete_atom_contributes_nothing(self) -> None:
        self.assertIsNone(
            assign_truncated_noun_branch(
                {"ordkl": "s."},
                self._tokens("best. pl."),
            )
        )


if __name__ == "__main__":
    unittest.main()
