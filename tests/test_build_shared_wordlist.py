from __future__ import annotations

import unittest

from swedish_wordlist_tools.build_shared_wordlist import build_rows


class BuildSharedWordlistTests(unittest.TestCase):
    def test_classified_form_suppresses_unknown_duplicate_and_context_is_omitted(self) -> None:
        records = [
            {"id":"n1","normaliserat_ord":"katt","ord":"katt","stycke":"katt","ordkl":"s. <i>+en +er</i>","text":"+en +er","upos":"NOUN"},
            {"id":"x1","normaliserat_ord":"katt","ord":"katten","stycke":"katten","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"x2","normaliserat_ord":"all","ord":"allom","stycke":"allom","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"x3","normaliserat_ord":"hux flux","ord":"flux","stycke":"flux","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        rows, summary = build_rows(records)
        by_form = {row["form"]: row for row in rows}
        self.assertEqual("CLASSIFIED", by_form["katten"]["classification"])
        self.assertEqual(["NOUN"], by_form["katten"]["upos"])
        self.assertEqual("UNKNOWN_WORD", by_form["allom"]["classification"])
        self.assertEqual(["X"], by_form["allom"]["upos"])
        self.assertNotIn("flux", by_form)
        self.assertEqual(1, summary["context_only_omitted"])

    def test_printed_variant_paradigm_is_included_as_classified(self) -> None:
        records = [
            {"id":"n1","normaliserat_ord":"annektion","homonr":"0","ord":"annexion","stycke":"an·nekt·ion","ordkl":"s. <i>+en +er</i>","text":"+en +er","upos":"NOUN"},
            {"id":"x1","normaliserat_ord":"annektion","homonr":"1","ord":"annexion","stycke":"annexion","ordkl":"(hv) <i>+en +er</i>","text":"+en +er","upos":"X"},
        ]
        rows, _summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual("CLASSIFIED", forms["annexion"]["classification"])
        self.assertEqual("CLASSIFIED", forms["annexionen"]["classification"])
        self.assertEqual("CLASSIFIED", forms["annexioner"]["classification"])

    def test_pronoun_generated_form_suppresses_hv_unknown(self) -> None:
        records = [
            {"id":"p1","normaliserat_ord":"all","ord":"all","stycke":"all","ordkl":"pron.","text":"+t +a","upos":"PRON"},
            {"id":"x1","normaliserat_ord":"all","ord":"alla","stycke":"alla","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        rows, summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual("CLASSIFIED", forms["alla"]["classification"])
        self.assertEqual(["PRON"], forms["alla"]["upos"])
        self.assertEqual(1, summary["unknown_suppressed_by_classified_duplicate"])
        self.assertIn("PRON", summary["classes"])

    def test_numeral_generated_form_suppresses_hv_unknown(self) -> None:
        records = [
            {"id":"m1","normaliserat_ord":"femtioen","ord":"femtioen","stycke":"femtioen","ordkl":"räkn.","text":"vid: uppräkning: ibl. femti(o)ett","upos":"NUM"},
            {"id":"x1","normaliserat_ord":"femtioen","ord":"femtioett","stycke":"femtioett","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        rows, summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual("CLASSIFIED", forms["femtioett"]["classification"])
        self.assertEqual(["NUM"], forms["femtioett"]["upos"])
        self.assertEqual(1, summary["unknown_suppressed_by_classified_duplicate"])
        self.assertIn("NUM", summary["classes"])

    def test_mixed_adv_adj_keeps_adv_lemma_but_inflects_only_adjective_role(self) -> None:
        records = [
            {"id":"a1","normaliserat_ord":"delvis","ord":"delvis","stycke":"del·vis","ordkl":"adv. och adj. <i>+t +a</i>","text":"+t +a","upos":"X"},
        ]
        rows, _summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual(["ADJ", "ADV"], forms["delvis"]["upos"])
        self.assertEqual(["ADJ"], forms["delvist"]["upos"])
        self.assertEqual(["ADJ"], forms["delvisa"]["upos"])

    def test_bound_adverbial_suffix_is_not_a_playable_word(self) -> None:
        rows, _summary = build_rows([
            {"id":"x1","normaliserat_ord":"-ledes","ord":"-ledes","stycke":"-led·es","ordkl":"adverbiellt slutled","text":None,"upos":"X"},
        ])
        self.assertEqual([], rows)


if __name__ == "__main__":
    unittest.main()
