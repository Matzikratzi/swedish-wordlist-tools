from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_numeral_forms import generated_row


class GenerateNumeralFormsTests(unittest.TestCase):
    def test_neuter_form(self) -> None:
        row = generated_row({"normaliserat_ord":"en","ord":"en","upos":"NUM","text":"n. ett"})
        self.assertEqual({"en","ett"}, {form["written_form"] for form in row["forms"]})

    def test_masculine_form(self) -> None:
        row = generated_row({"normaliserat_ord":"första","ord":"första","upos":"NUM","text":"mask. förste"})
        self.assertEqual({"första","förste"}, {form["written_form"] for form in row["forms"]})

    def test_parenthetical_o_is_expanded(self) -> None:
        row = generated_row({"normaliserat_ord":"femtioen","ord":"femtioen","upos":"NUM","text":"vid: uppräkning: ibl. femti(o)ett"})
        self.assertEqual({"femtioen","femtiett","femtioett"}, {form["written_form"] for form in row["forms"]})

    def test_null_text_is_lemma_only(self) -> None:
        row = generated_row({"normaliserat_ord":"fem","ord":"fem","upos":"NUM","text":"(null)"})
        self.assertEqual(["fem"], [form["written_form"] for form in row["forms"]])

    def test_printed_variant_is_base(self) -> None:
        row = generated_row({"normaliserat_ord":"ettusen","ord":"etttusen","homonr":"0","upos":"NUM","text":"(null)"})
        self.assertEqual(["etttusen"], [form["written_form"] for form in row["forms"]])


if __name__ == "__main__":
    unittest.main()
