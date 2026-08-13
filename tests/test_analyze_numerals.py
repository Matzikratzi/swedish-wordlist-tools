from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_numerals import analyze


class AnalyzeNumeralsTests(unittest.TestCase):
    def test_groups_notation_and_marks_printed_variant(self) -> None:
        records = [
            {"id":"1","normaliserat_ord":"första","ord":"första","upos":"NUM","ordkl":"räkn.","text":"mask. förste"},
            {"id":"2","normaliserat_ord":"första","ord":"förste","upos":"NUM","ordkl":"räkn.","text":"mask. förste"},
            {"id":"3","normaliserat_ord":"ett","ord":"ett","upos":"NUM","ordkl":"räkn.","text":None},
        ]
        report = analyze(records)
        self.assertEqual(3, report["numeral_records"])
        self.assertEqual(1, report["empty_text_records"])
        self.assertEqual(1, report["printed_variant_records"])
        self.assertEqual(2, report["unique_notations"])
        group = next(group for group in report["groups"] if group["notation"] == "mask. förste")
        self.assertEqual(2, group["count"])


if __name__ == "__main__":
    unittest.main()
