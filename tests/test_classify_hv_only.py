from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_hv_only import CONTEXT_ONLY, UNKNOWN_WORD, analyze, classify_case


class ClassifyHvOnlyTests(unittest.TestCase):
    def test_standalone_hv_only_form_becomes_unknown_word(self) -> None:
        classification, reason = classify_case({"form":"allom","hv_lemma":"all"})
        self.assertEqual(UNKNOWN_WORD, classification)
        self.assertEqual("standalone_hv_only_form", reason)

    def test_fragment_of_multiword_expression_is_context_only(self) -> None:
        classification, reason = classify_case({"form":"flux","hv_lemma":"hux flux"})
        self.assertEqual(CONTEXT_ONLY, classification)
        self.assertEqual("strict_part_of_multiword_lemma", reason)

    def test_multiword_hv_form_itself_is_context_only(self) -> None:
        classification, reason = classify_case({"form":"in pleno","hv_lemma":"plenum"})
        self.assertEqual(CONTEXT_ONLY, classification)
        self.assertEqual("printed_form_is_multiword", reason)

    def test_analysis_never_inflects_unknown_words(self) -> None:
        records = [
            {"id":"x1","normaliserat_ord":"all","ord":"allom","stycke":"allom","ordkl":"(hv)","text":None,"upos":"X"},
            {"id":"x2","normaliserat_ord":"hux flux","ord":"flux","stycke":"flux","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        report = analyze(records)
        by_form = {row["form"]: row for row in report["rows"]}
        self.assertEqual(UNKNOWN_WORD, by_form["allom"]["classification"])
        self.assertEqual("X", by_form["allom"]["upos"])
        self.assertFalse(by_form["allom"]["generate_inflections"])
        self.assertEqual(CONTEXT_ONLY, by_form["flux"]["classification"])
        self.assertIsNone(by_form["flux"]["upos"])
        self.assertFalse(by_form["flux"]["generate_inflections"])


if __name__ == "__main__":
    unittest.main()
