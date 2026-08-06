from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import (
    FormOperationKind,
    expand_optional_form_token,
    parse_form_operations,
)
from swedish_wordlist_tools.verb_slots import interpret_verb_slots


class OptionalFormTokenTests(unittest.TestCase):
    def test_expands_arbitrary_optional_segments(self) -> None:
        cases = {
            "+(e)n": ("+n", "+en"),
            "håll(e)s": ("hålls", "hålles"),
            "fyrti(o)förste": ("fyrtiförste", "fyrtioförste"),
            "-ab(cd)ef": ("-abef", "-abcdef"),
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                self.assertEqual(expected, expand_optional_form_token(token))

    def test_parses_explicit_and_operation_variants(self) -> None:
        explicit = parse_form_operations("håll(e)s")
        self.assertIsNotNone(explicit)
        assert explicit is not None
        self.assertEqual(
            ((FormOperationKind.EXPLICIT, "hålls"), (FormOperationKind.EXPLICIT, "hålles")),
            tuple((operation.kind, operation.value) for operation in explicit),
        )

        appended = parse_form_operations("+(e)n")
        self.assertIsNotNone(appended)
        assert appended is not None
        self.assertEqual(
            ((FormOperationKind.APPEND, "n"), (FormOperationKind.APPEND, "en")),
            tuple((operation.kind, operation.value) for operation in appended),
        )

    def test_interprets_hallas_optional_present_vowel(self) -> None:
        slots = interpret_verb_slots(
            {
                "normaliserat_ord": "hållas",
                "homonr": "1",
                "ordkl": "v.",
                "stycke": "håll·as",
                "text": "hölls, hållits, pres. håll(e)s",
                "upos": "VERB",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("hålls", "hålles"), slots.forms_for("present"))
        self.assertEqual(("hölls",), slots.forms_for("preterite"))
        self.assertEqual(("hållits",), slots.forms_for("supine"))

    def test_parenthetical_prose_is_still_a_comment(self) -> None:
        slots = interpret_verb_slots(
            {
                "normaliserat_ord": "ana",
                "ordkl": "v.",
                "stycke": "ana",
                "text": "+de el. (i: ett: uttryck:) ante, +t",
                "upos": "VERB",
            }
        )
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("anade", "ante"), slots.forms_for("preterite"))
        self.assertEqual(("anat",), slots.forms_for("supine"))


if __name__ == "__main__":
    unittest.main()
