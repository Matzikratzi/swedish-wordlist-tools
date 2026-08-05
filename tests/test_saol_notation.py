from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import (
    FormOperationKind,
    apply_form_operation,
    assign_labeled_slots,
    parse_form_operation,
    tokenize_notation,
)


class SaolNotationTests(unittest.TestCase):
    def test_parses_primitive_form_operations(self) -> None:
        cases = {
            "+": (FormOperationKind.UNCHANGED, ""),
            "+a": (FormOperationKind.APPEND, "a"),
            "+-t": (FormOperationKind.APPEND, "t"),
            "-bundna": (FormOperationKind.REPLACE_TAIL, "bundna"),
            "bättre": (FormOperationKind.EXPLICIT, "bättre"),
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                operation = parse_form_operation(token)
                self.assertIsNotNone(operation)
                assert operation is not None
                self.assertEqual(expected, (operation.kind, operation.value))

    def test_preserves_spelling_in_noun_operations(self) -> None:
        cases = {
            "+:n": (FormOperationKind.APPEND, ":n"),
            "+:ar": (FormOperationKind.APPEND, ":ar"),
            "-Klockor": (FormOperationKind.REPLACE_TAIL, "Klockor"),
            "-änder": (FormOperationKind.REPLACE_TAIL, "änder"),
            "+<k>s</k>": (FormOperationKind.APPEND, "s"),
            "A-kassor": (FormOperationKind.EXPLICIT, "A-kassor"),
            "BB:t": (FormOperationKind.EXPLICIT, "BB:t"),
            "señoror": (FormOperationKind.EXPLICIT, "señoror"),
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                operation = parse_form_operation(token)
                self.assertIsNotNone(operation)
                assert operation is not None
                self.assertEqual(expected, (operation.kind, operation.value))

    def test_tokenizer_keeps_payloads_atomic(self) -> None:
        self.assertEqual(("+:n", "+:ar"), tokenize_notation("+:n +:ar"))
        self.assertEqual(("+en", "-änder"), tokenize_notation("+en -änder"))
        self.assertEqual(("BB:t", ";", "pl.", "BB:n"), tokenize_notation("BB:t; pl. BB:n"))
        self.assertEqual(("+t", ";", "pl.", "+", "H", "+s"), tokenize_notation("+t; pl. + H +<k>s</k>"))

    def test_rejects_labels_and_separators_as_form_operations(self) -> None:
        for token in ("komp.", "pl.", "el.", "_", "["):
            with self.subTest(token=token):
                self.assertIsNone(parse_form_operation(token))

    def test_assigns_common_labels_to_supplied_slots(self) -> None:
        assigned = assign_labeled_slots(
            ("+n", ";", "pl.", "+", "el.", "-metrar", ",", "best.", "pl.", "+na"),
            singular_slot="sg_def",
            plural_slot="pl_indef",
            definite_plural_slot="pl_def",
        )
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual(
            (
                ("sg_def", "+n"),
                ("pl_indef", "+"),
                ("pl_indef", "-metrar"),
                ("pl_def", "+na"),
            ),
            tuple((item.slot, item.token) for item in assigned),
        )

    def test_rejects_unmarked_explicit_prose_as_slot_sequence(self) -> None:
        self.assertIsNone(
            assign_labeled_slots(
                ("helt", "okänd", "notation"),
                singular_slot="sg_def",
                plural_slot="pl_indef",
                definite_plural_slot="pl_def",
            )
        )

    def test_applies_default_operations(self) -> None:
        self.assertEqual("blå", apply_form_operation("blå", parse_form_operation("+")))
        self.assertEqual("blåa", apply_form_operation("blå", parse_form_operation("+a")))
        self.assertEqual("bättre", apply_form_operation("god", parse_form_operation("bättre")))

    def test_delegates_ordklass_specific_realization(self) -> None:
        operation = parse_form_operation("+t")
        self.assertIsNotNone(operation)
        assert operation is not None
        result = apply_form_operation(
            "glad",
            operation,
            append=lambda base, suffix: "glatt" if (base, suffix) == ("glad", "t") else base + suffix,
        )
        self.assertEqual("glatt", result)

        replacement = parse_form_operation("-bundna")
        self.assertIsNotNone(replacement)
        assert replacement is not None
        self.assertEqual(
            "obundna",
            apply_form_operation(
                "obunden",
                replacement,
                replace_tail=lambda base, tail: "obundna" if (base, tail) == ("obunden", "bundna") else None,
            ),
        )

    def test_prefers_explicit_replacement_handler_to_overlap_guess(self) -> None:
        replacement = parse_form_operation("-klockor")
        self.assertIsNotNone(replacement)
        assert replacement is not None
        self.assertEqual(
            "alarmklockor",
            apply_form_operation(
                "alarmklocka",
                replacement,
                replace_tail=lambda _base, _tail: "alarmklockor",
            ),
        )


if __name__ == "__main__":
    unittest.main()
