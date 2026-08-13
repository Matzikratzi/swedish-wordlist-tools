from __future__ import annotations

import unittest

from swedish_wordlist_tools.audit_ignore_hv import analyze


class AuditIgnoreHvTests(unittest.TestCase):
    def test_classifies_explicit_generated_text_and_hv_only_forms(self) -> None:
        records = [
            {"id":"n1","normaliserat_ord":"katt","ord":"katt","stycke":"katt","ordkl":"s. <i>+en +er</i>","text":"+en +er","upos":"NOUN"},
            {"id":"x1","normaliserat_ord":"katt","ord":"katten","stycke":"katten","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"a1","normaliserat_ord":"snäll","ord":"snäll","stycke":"snäll","ordkl":"adj. <i>+t +a</i>","text":"+t +a specialform","upos":"ADJ"},
            {"id":"x2","normaliserat_ord":"snäll","ord":"specialform","stycke":"specialform","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"i1","normaliserat_ord":"hej","ord":"hejsan","stycke":"hejsan","ordkl":"interj.","text":None,"upos":"X"},
            {"id":"x3","normaliserat_ord":"hej","ord":"hejsan","stycke":"hejsan","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"x4","normaliserat_ord":"fras","ord":"lösdel","stycke":"lösdel","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        report = analyze(records)
        by_form = {}
        for case in report["cases"]:
            by_form.setdefault(case["form"], set()).add(case["status"])
        self.assertIn("generated_from_real_row", by_form["katten"])
        self.assertIn("mentioned_in_real_text", by_form["specialform"])
        self.assertIn("explicit_real_row", by_form["hejsan"])
        self.assertIn("hv_only", by_form["lösdel"])
        self.assertEqual(1, report["unique_hv_only_forms"])

    def test_textless_hv_variant_is_recovered_by_real_variant_row(self) -> None:
        records = [
            {"id":"r1","normaliserat_ord":"Budda","homonr":"0","ord":"Buddha","ordkl":"namn","text":None,"upos":"X"},
            {"id":"x1","normaliserat_ord":"Budda","homonr":"1","ord":"Buddha","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        report = analyze(records)
        cases = [case for case in report["cases"] if case["form"] == "Buddha"]
        self.assertEqual("explicit_real_row", cases[0]["status"])
        self.assertEqual(0, report["unique_hv_only_forms"])

    def test_real_homonr_zero_noun_variant_generates_from_printed_ord(self) -> None:
        records = [
            {"id":"r1","normaliserat_ord":"annektion","homonr":"0","ord":"annexion","stycke":"annektion","ordkl":"s. <i>+en +er</i>","text":"+en +er","upos":"NOUN"},
            {"id":"x1","normaliserat_ord":"annektion","homonr":"1","ord":"annexion","stycke":"annexion","ordkl":"(hv) <i>+en +er</i>","text":"+en +er","upos":"X"},
        ]
        report = analyze(records)
        by_form = {case["form"]: case["status"] for case in report["cases"]}
        self.assertEqual("explicit_real_row", by_form["annexion"])
        self.assertEqual("generated_from_real_row", by_form["annexionen"])
        self.assertEqual("generated_from_real_row", by_form["annexioner"])
        self.assertEqual(0, report["unique_hv_only_forms"])


if __name__ == "__main__":
    unittest.main()
