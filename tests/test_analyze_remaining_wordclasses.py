from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_remaining_wordclasses import analyze


class AnalyzeRemainingWordclassesTests(unittest.TestCase):
    def test_only_unsupported_x_entry_remains(self) -> None:
        records = [
            {"ord":"bakom","ordkl":"prep.","text":None,"upos":"ADP"},
            {"ord":"både","ordkl":"konj.","text":None,"upos":"CCONJ"},
            {"ord":"adjö","ordkl":"interj.","text":None,"upos":"INTJ"},
            {"ord":"Afrika","ordkl":"namn","text":None,"upos":"PROPN"},
            {"ord":"alltsedan","ordkl":"subj.","text":None,"upos":"SCONJ"},
            {"ord":"den","ordkl":"best. artikel","text":"n. det; pl. de, vard. dom [dåm>]","upos":"X"},
            {"ord":"att","ordkl":"infinitivmärke","text":None,"upos":"X"},
            {"ord":"super","ordkl":"i sms.","text":None,"upos":"X"},
        ]

        report = analyze(records)

        self.assertEqual({"X": 1}, report["counts"])
        self.assertEqual("super", report["examples"]["X"][0]["ord"])


if __name__ == "__main__":
    unittest.main()
