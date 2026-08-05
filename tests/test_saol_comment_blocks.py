from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import (
    FormOperationKind,
    assign_labeled_slots,
    tokenize_notation,
)


class SaolCommentBlockTests(unittest.TestCase):
    def assigned(self, text: str):
        tokens = tokenize_notation(text)
        self.assertIsNotNone(tokens)
        assert tokens is not None
        assigned = assign_labeled_slots(
            tokens,
            singular_slot="singular",
            plural_slot="plural",
            definite_plural_slot="definite_plural",
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        return assigned

    def test_keeps_forms_around_parenthesized_comment(self) -> None:
        assigned = self.assigned("+de el. (i: ett: uttryck:) ante, +t")
        self.assertEqual(
            (
                (FormOperationKind.APPEND, "de"),
                (FormOperationKind.EXPLICIT, "ante"),
                (FormOperationKind.APPEND, "t"),
            ),
            tuple((item.operation.kind, item.operation.value) for item in assigned),
        )

    def test_keeps_operation_after_comment_phrase(self) -> None:
        assigned = self.assigned("best. +; i: pl. används: -ansökningar")
        self.assertEqual(
            (
                (FormOperationKind.UNCHANGED, ""),
                (FormOperationKind.REPLACE_TAIL, "ansökningar"),
            ),
            tuple((item.operation.kind, item.operation.value) for item in assigned),
        )

    def test_keeps_explicit_form_after_comment_and_generic_label(self) -> None:
        assigned = self.assigned("+n; i: vissa: uttryck: gen. herrans")
        self.assertEqual(
            (
                (FormOperationKind.APPEND, "n"),
                (FormOperationKind.EXPLICIT, "herrans"),
            ),
            tuple((item.operation.kind, item.operation.value) for item in assigned),
        )

    def test_colons_inside_forms_and_operations_are_not_comments(self) -> None:
        assigned = self.assigned("+:n BB:t")
        self.assertEqual(
            (
                (FormOperationKind.APPEND, ":n"),
                (FormOperationKind.EXPLICIT, "BB:t"),
            ),
            tuple((item.operation.kind, item.operation.value) for item in assigned),
        )


if __name__ == "__main__":
    unittest.main()
