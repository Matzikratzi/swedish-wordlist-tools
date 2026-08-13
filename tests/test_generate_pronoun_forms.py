from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_pronoun_forms import generated_row


class GeneratePronounFormsTests(unittest.TestCase):
    def test_simple_possessive_forms(self) -> None:
        row = generated_row({"normaliserat_ord":"din","ord":"din","upos":"PRON","ordkl":"pron.","text":"ditt dina"})
        self.assertIsNotNone(row)
        self.assertEqual({"din","ditt","dina"}, {form["written_form"] for form in row["forms"]})

    def test_truncated_personal_pronoun_keeps_visible_object_form(self) -> None:
        text = "sing. objektsform: mig uttalat: och: också: vard."
        row = generated_row({"normaliserat_ord":"jag","ord":"jag","upos":"PRON","ordkl":"pron.","text":text})
        self.assertIsNotNone(row)
        self.assertIn("mig", {form["written_form"] for form in row["forms"]})
        self.assertTrue(row["source_truncated"])
        self.assertFalse(row["paradigm_complete"])

    def test_suffix_operations_and_explicit_alternatives(self) -> None:
        row = generated_row({"normaliserat_ord":"sådan","ord":"sådan","upos":"PRON","ordkl":"pron.","text":"+t +a _ sånt såna"})
        self.assertIsNotNone(row)
        forms = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"sådan","sådant","sådana","sånt","såna"} <= forms)

    def test_empty_pronoun_row_is_lemma_only(self) -> None:
        row = generated_row({"normaliserat_ord":"båda","ord":"båda","upos":"PRON","ordkl":"pron.","text":""})
        self.assertEqual(["båda"], [form["written_form"] for form in row["forms"]])

    def test_printed_variant_is_inflection_base(self) -> None:
        row = generated_row({"normaliserat_ord":"sådan","ord":"sån","homonr":"0","upos":"PRON","ordkl":"pron.","text":"+t +a _ sånt såna"})
        forms = {form["written_form"] for form in row["forms"]}
        self.assertIn("sån", forms)
        self.assertIn("sånt", forms)
        self.assertIn("såna", forms)
        self.assertNotIn("sådan", forms)


if __name__ == "__main__":
    unittest.main()
