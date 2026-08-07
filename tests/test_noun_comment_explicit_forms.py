from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_row_interpreter import interpret_noun_row


class NounCommentExplicitFormsTests(unittest.TestCase):
    @staticmethod
    def record(lemma: str, text: str, stycke: str = "") -> dict[str, str]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke or lemma,
            "ordkl": "s.",
            "upos": "NOUN",
        }

    @staticmethod
    def forms(row) -> set[str]:
        return {form.written_form for form in row.key_forms} if row else set()

    def test_keeps_explicit_plural_after_parenthesized_comment(self) -> None:
        rubel = interpret_noun_row(
            self.record(
                "rubel",
                "+n; pl. + el. (mest: om: enstaka: mynt:) rubler",
            )
        )
        self.assertIsNotNone(rubel)
        self.assertTrue({"rubel", "rubeln", "rubler"} <= self.forms(rubel))
        self.assertTrue({"mest", "om", "enstaka", "mynt"}.isdisjoint(self.forms(rubel)))

        tempo = interpret_noun_row(
            self.record(
                "tempo",
                "+t; pl. +n el. (mest: i: fråga: om: musik:) tempi",
            )
        )
        self.assertIsNotNone(tempo)
        self.assertTrue({"tempo", "tempot", "tempon", "tempi"} <= self.forms(tempo))
        self.assertTrue({"mest", "i", "fråga", "om", "musik"}.isdisjoint(self.forms(tempo)))

    def test_comment_word_that_is_another_lemma_is_not_a_form(self) -> None:
        row = interpret_noun_row(
            self.record(
                "gips",
                "+en om: gipsförband: ibl. +et; pl. +er",
            )
        )
        self.assertIsNotNone(row)
        self.assertTrue({"gips", "gipsen", "gipset", "gipser"} <= self.forms(row))
        self.assertNotIn("gipsförband", self.forms(row))

    def test_explicit_full_form_is_not_tail_replacement(self) -> None:
        row = interpret_noun_row(self.record("señora", "+n señoror", "señ·ora"))
        self.assertIsNotNone(row)
        self.assertTrue({"señora", "señoran", "señoror"} <= self.forms(row))
        self.assertNotIn("oror", self.forms(row))


if __name__ == "__main__":
    unittest.main()
