from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_numeral_forms import generated_row


class GenerateNumeralOptionalFormsTests(unittest.TestCase):
    def test_optional_o_generates_both_counting_forms(self) -> None:
        row = generated_row({
            "normaliserat_ord": "femtioen",
            "ord": "femtioen",
            "upos": "NUM",
            "text": "vid: uppräkning: ibl. femti(o)ett",
        })
        self.assertEqual(
            {"femtioen", "femtiett", "femtioett"},
            {form["written_form"] for form in row["forms"]},
        )

    def test_optional_o_generates_both_masculine_forms(self) -> None:
        row = generated_row({
            "normaliserat_ord": "femtioförsta",
            "ord": "femtioförsta",
            "upos": "NUM",
            "text": "mask. femti(o)förste",
        })
        self.assertEqual(
            {"femtioförsta", "femtiförste", "femtioförste"},
            {form["written_form"] for form in row["forms"]},
        )


if __name__ == "__main__":
    unittest.main()
