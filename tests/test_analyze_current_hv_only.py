from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_current_hv_only import analyze


class AnalyzeCurrentHvOnlyTests(unittest.TestCase):
    def test_numeral_recovered_from_historical_hv_only(self) -> None:
        records = [
            {"id":"n1","normaliserat_ord":"femtioen","ord":"femtioen","ordkl":"räkn.","text":"vid: uppräkning: ibl. femti(o)ett","upos":"NUM"},
            {"id":"x1","normaliserat_ord":"femtioen","ord":"femtioett","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        report = analyze(records)
        self.assertEqual(1, report["historical_hv_only"])
        self.assertEqual(1, report["recovered_by_current_extra_shared"])
        self.assertEqual(0, report["current_hv_only"])
        self.assertEqual(["NUM"], report["recovered"][0]["recovered_by"])

    def test_routed_hv_form_is_recovered_by_the_production_builder(self) -> None:
        records = [
            {"id":"p1","normaliserat_ord":"all","homonr":"1","ord":"all","ordkl":"pron. <i>+t +a</i>","text":"+t +a","upos":"PRON"},
            {"id":"x1","normaliserat_ord":"all","homonr":"0","ord":"alle","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        report = analyze(records)
        self.assertEqual(1, report["historical_hv_only"])
        self.assertEqual(1, report["recovered_by_current_shared"])
        self.assertEqual(0, report["current_hv_only"])
        self.assertEqual(["PRON"], report["recovered"][0]["recovered_by"])


if __name__ == "__main__":
    unittest.main()
