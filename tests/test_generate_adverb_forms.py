from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_adverb_forms import generated_row


class GenerateAdverbFormsTests(unittest.TestCase):
    def test_lemma_only_row(self) -> None:
        row = generated_row({"normaliserat_ord":"absolut","ord":"absolut","upos":"ADV","ordkl":"adv.","text":None})
        self.assertEqual(["absolut"], [form["written_form"] for form in row["forms"]])

    def test_suffix_comparison(self) -> None:
        row = generated_row({"normaliserat_ord":"ofta","ord":"ofta","upos":"ADV","ordkl":"adv.","text":"komp. +re, superl. +st"})
        forms = {form["written_form"] for form in row["forms"]}
        self.assertEqual({"ofta","oftare","oftast"}, forms)

    def test_explicit_irregular_comparison(self) -> None:
        row = generated_row({"normaliserat_ord":"väl","ord":"väl","upos":"ADV","ordkl":"adv.","text":"bättre bäst"})
        forms = {form["written_form"] for form in row["forms"]}
        self.assertEqual({"väl","bättre","bäst"}, forms)

    def test_truncated_near_keeps_only_visible_forms(self) -> None:
        text = "komp. närmare el. närmre, superl. närmast el. närm"
        row = generated_row({"normaliserat_ord":"nära","ord":"nära","upos":"ADV","ordkl":"adv.","text":text})
        forms = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"nära","närmare","närmre","närmast","närm"} <= forms)
        self.assertTrue(row["source_truncated"])
        self.assertFalse(row["paradigm_complete"])

    def test_printed_variant_is_base(self) -> None:
        row = generated_row({"normaliserat_ord":"vis","ord":"viss","homonr":"0","upos":"ADV","ordkl":"adv.","text":"+t +a"})
        forms = {form["written_form"] for form in row["forms"]}
        self.assertIn("viss", forms)
        self.assertIn("visst", forms)
        self.assertNotIn("vis", forms)


if __name__ == "__main__":
    unittest.main()
