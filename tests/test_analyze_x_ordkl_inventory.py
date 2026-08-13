from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_x_ordkl_inventory import analyze, ordkl_head


class AnalyzeXOrdklInventoryTests(unittest.TestCase):
    def test_ordkl_head_uses_saol_class_before_inflection_copy(self) -> None:
        self.assertEqual("adv.", ordkl_head({"ordkl": "adv. <i>bättre, bäst</i>"}))
        self.assertEqual("adv. och adj.", ordkl_head({"ordkl": "adv. och adj. <i>+t +a</i>"}))
        self.assertEqual("(hv)", ordkl_head({"ordkl": "(hv) <i>+en +er</i>"}))

    def test_x_records_are_grouped_by_ordkl(self) -> None:
        report = analyze([
            {"upos": "X", "normaliserat_ord": "bra", "ordkl": "adv. <i>bättre, bäst</i>", "text": "bättre, bäst"},
            {"upos": "X", "normaliserat_ord": "nu", "ordkl": "adv.", "text": None},
            {"upos": "X", "normaliserat_ord": "ansatsvis", "ordkl": "adv. och adj. <i>+t +a</i>", "text": "+t +a"},
            {"upos": "PRON", "normaliserat_ord": "din", "ordkl": "pron.", "text": "ditt dina"},
        ])
        self.assertEqual(3, report["x_records"])
        self.assertEqual(2, report["text_records"])
        groups = {row["ordkl"]: row for row in report["groups"]}
        self.assertEqual(2, groups["adv."]["records"])
        self.assertEqual(1, groups["adv."]["text_records"])
        self.assertEqual(1, groups["adv. och adj."]["text_records"])


if __name__ == "__main__":
    unittest.main()
