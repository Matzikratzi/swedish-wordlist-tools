from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import (
    FormOperationKind,
    parse_form_operations,
)
from swedish_wordlist_tools.saol_row_interpreter import interpret_noun_row


class RemainingNounNotationPatternsTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str = "") -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "upos": "NOUN",
            "ordkl": "s.",
            "text": text,
            "stycke": stycke,
        }

    def test_expands_arbitrary_optional_operation_payload(self) -> None:
        operations = parse_form_operations("+ab(cd)ef")
        self.assertIsNotNone(operations)
        assert operations is not None
        self.assertEqual(
            (
                (FormOperationKind.APPEND, "abef"),
                (FormOperationKind.APPEND, "abcdef"),
            ),
            tuple((operation.kind, operation.value) for operation in operations),
        )

    def test_interprets_optional_definite_suffix_for_essa(self) -> None:
        row = interpret_noun_row(
            self.record("essä", "+n +er _ +(e)n [esä>n]; pl. +er", "essä")
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(
            {"essän", "essäen"},
            {
                form.written_form
                for form in row.key_forms
                if form.slot == "sg_def"
            },
        )
        self.assertEqual(
            {"essäer"},
            {
                form.written_form
                for form in row.key_forms
                if form.slot == "pl_indef"
            },
        )

    def test_applies_repeated_payload_to_final_hyphen_component(self) -> None:
        row = interpret_noun_row(
            self.record(
                "användar-id",
                "+id:t el. +id:n; pl. +id:n _ +ID:t el. +ID:n; pl.",
                "an·vänd·ar-id",
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        written = {form.written_form for form in row.key_forms}
        self.assertIn("användar-id:t", written)
        self.assertIn("användar-id:n", written)
        self.assertIn("användar-ID:t", written)
        self.assertIn("användar-ID:n", written)
        self.assertNotIn("användar-idid", written)
        self.assertNotIn("användar-idID", written)

    def test_keeps_full_explicit_plural_for_hyphenated_lemma(self) -> None:
        row = interpret_noun_row(
            self.record(
                "tio-i-topp-lista",
                "+n tio-i-topp-listor",
                "tio-i-topp-lista",
            )
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual("tio-i-topp-listor", row.form("pl_indef"))


if __name__ == "__main__":
    unittest.main()
