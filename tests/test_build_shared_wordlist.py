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

    def test_lemma_only_classes_add_only_the_printed_word(self) -> None:
        records = [
            {"id":"p1","normaliserat_ord":"bakom","ord":"bak|om","stycke":"bak|om","ordkl":"prep.","text":None,"upos":"ADP"},
            {"id":"i1","normaliserat_ord":"adjö","ord":"adjö","stycke":"adjö","ordkl":"interj.","text":None,"upos":"INTJ"},
            {"id":"n1","normaliserat_ord":"Afrika","ord":"Afrika","stycke":"Afrika","ordkl":"namn","text":None,"upos":"PROPN"},
        ]
        rows, summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual(["ADP"], forms["bakom"]["upos"])
        self.assertEqual(["INTJ"], forms["adjö"]["upos"])
        self.assertEqual(["PROPN"], forms["Afrika"]["upos"])
        self.assertEqual({"ADP", "INTJ", "PROPN"}, set(summary["classes"]) & {"ADP", "INTJ", "PROPN"})

    def test_mixed_adp_sconj_keeps_both_roles_and_sms_entry_is_omitted(self) -> None:
        records = [
            {"id":"m1","normaliserat_ord":"alltsedan","ord":"allt|sed·an","stycke":"allt|sed·an","ordkl":"prep. och subj.","text":None,"upos":"X"},
            {"id":"x1","normaliserat_ord":"super","ord":"super","stycke":"super","ordkl":"i sms.","text":None,"upos":"X"},
        ]
        rows, _summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        self.assertEqual(["ADP", "SCONJ"], forms["alltsedan"]["upos"])
        self.assertNotIn("super", forms)


    def test_articles_and_infinitive_marker_keep_explicit_classification(self) -> None:
        records = [
            {"id":"d1","normaliserat_ord":"den","ord":"den","stycke":"den","ordkl":"best. artikel","text":"n. det; pl. de, vard. dom [dåm>]","upos":"X"},
            {"id":"e1","normaliserat_ord":"en","ord":"en","stycke":"en","ordkl":"obest. artikel","text":"n. ett","upos":"X"},
            {"id":"h1","normaliserat_ord":"hin","ord":"hin","stycke":"hin","ordkl":"best. artikel","text":None,"upos":"X"},
            {"id":"a1","normaliserat_ord":"att","ord":"att","stycke":"att","ordkl":"infinitivmärke","text":None,"upos":"X"},
        ]
        rows, summary = build_rows(records)
        forms = {row["form"]: row for row in rows}
        for form in ("den", "det", "de", "dom", "en", "ett", "hin"):
            self.assertEqual(["DET"], forms[form]["upos"])
        self.assertEqual(["PART"], forms["att"]["upos"])
        self.assertNotIn("dåm", forms)
        self.assertEqual({"DET", "PART"}, set(summary["classes"]) & {"DET", "PART"})


if __name__ == "__main__":
    unittest.main()
