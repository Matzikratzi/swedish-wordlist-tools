from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_pronouns import analyze


class AnalyzePronounsTests(unittest.TestCase):
    def test_inventory_counts_pronouns_and_variants(self) -> None:
        records = [
            {"id":"p1","normaliserat_ord":"jag","ord":"jag","homonr":"1","ordkl":"pron. <i>sing. objektsform: mig</i>","text":"sing. objektsform: mig","upos":"PRON"},
            {"id":"p2","normaliserat_ord":"någon","ord":"nån","homonr":"0","ordkl":"pron. <i>något några</i>","text":"något några","upos":"PRON"},
            {"id":"n1","normaliserat_ord":"katt","ord":"katt","homonr":"1","ordkl":"s. <i>+en +er</i>","text":"+en +er","upos":"NOUN"},
        ]
        report = analyze(records)
        self.assertEqual(2, report["pronoun_records"])
        self.assertEqual(1, report["printed_variant_records"])
        self.assertEqual(0, report["empty_text_records"])
        self.assertEqual(2, report["notation_shapes"])

    def test_empty_pronoun_text_is_kept_visible(self) -> None:
        report = analyze([
            {"id":"p1","normaliserat_ord":"x","ord":"x","homonr":"1","ordkl":"pron.","text":None,"upos":"PRON"},
        ])
        self.assertEqual(1, report["empty_text_records"])
        self.assertEqual(1, report["shape_counts"][""])


if __name__ == "__main__":
    unittest.main()
