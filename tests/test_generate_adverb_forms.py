from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adverb_oftare import analyze as analyze_ofta_family
from swedish_wordlist_tools.generate_adverb_forms import generated_row


class GenerateAdverbFormsTests(unittest.TestCase):
    def test_exact_pure_adverb_row_is_lemma_only(self) -> None:
        row = generated_row({"normaliserat_ord":"absolut","ord":"absolut","upos":"ADV","ordkl":"adv.","text":None})
        self.assertEqual(["absolut"], [form["written_form"] for form in row["forms"]])

    def test_exact_pure_adverb_does_not_invent_inflection_from_text(self) -> None:
        row = generated_row({"normaliserat_ord":"absolut","ord":"absolut","upos":"ADV","ordkl":"adv.","text":"+t +a"})
        self.assertEqual(["absolut"], [form["written_form"] for form in row["forms"]])

    def test_explicit_suffix_comparison(self) -> None:
        row = generated_row({
            "normaliserat_ord":"ofta","ord":"ofta","upos":"ADV",
            "ordkl":"adv. <i>komp. +re, superl. +st</i>",
            "text":"komp. +re, superl. +st",
        })
        forms = {form["written_form"] for form in row["forms"]}
        self.assertEqual({"ofta","oftare","oftast"}, forms)

    def test_explicit_irregular_comparison(self) -> None:
        row = generated_row({
            "normaliserat_ord":"väl","ord":"väl","upos":"ADV",
            "ordkl":"adv. <i>bättre bäst</i>","text":"bättre bäst",
        })
        forms = {form["written_form"] for form in row["forms"]}
        self.assertEqual({"väl","bättre","bäst"}, forms)

    def test_truncated_near_keeps_only_visible_forms(self) -> None:
        text = "komp. närmare el. närmre, superl. närmast el. närm"
        row = generated_row({
            "normaliserat_ord":"nära","ord":"nära","upos":"ADV",
            "ordkl":f"adv. <i>{text}</i>","text":text,
        })
        forms = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"nära","närmare","närmre","närmast","närm"} <= forms)
        self.assertTrue(row["source_truncated"])
        self.assertFalse(row["paradigm_complete"])

    def test_ofta_family_audit_finds_hv_only_comparative(self) -> None:
        report = analyze_ofta_family([
            {"id":"a1","normaliserat_ord":"ofta","ord":"ofta","ordkl":"adv.","text":None,"upos":"ADV"},
            {"id":"x1","normaliserat_ord":"ofta","ord":"oftare","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"a2","normaliserat_ord":"oftast","ord":"oftast","ordkl":"adv.","text":None,"upos":"ADV"},
        ])
        self.assertEqual(3, len(report["matching_records"]))
        self.assertEqual("oftare", report["hv_only_rows"][0]["form"])


if __name__ == "__main__":
    unittest.main()
