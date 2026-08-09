from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_ordkl_field import build_summary, render


class AnalyzeOrdklFieldTests(unittest.TestCase):
    def test_reports_length_limit_and_name_upos(self) -> None:
        capped = "s. " + "x" * 27
        self.assertEqual(30, len(capped))
        rows = [
            {
                "normaliserat_ord": "Kanarieöarna",
                "homonr": "1",
                "ordkl": "namn",
                "upos": "X",
                "text": "(null)",
                "subnr": 1,
            },
            {
                "normaliserat_ord": "Testnamn",
                "homonr": "1",
                "ordkl": "namn",
                "upos": "NOUN",
                "text": "(null)",
                "subnr": 2,
            },
            {
                "normaliserat_ord": "lång",
                "ordkl": capped,
                "upos": "X",
                "text": "(null)",
                "subnr": 3,
            },
        ]
        summary = build_summary(rows)
        self.assertEqual(30, summary["max_ordkl_length"])
        self.assertEqual(1, summary["ordkl_at_suspected_limit"])
        self.assertEqual(1, summary["unique_ordkl_at_suspected_limit"])
        self.assertEqual(2, summary["name_records"])
        self.assertEqual({"X": 1, "NOUN": 1}, summary["name_raw_upos"])
        self.assertEqual({"PROPN": 2}, summary["name_resolved_upos"])
        text = render(summary)
        self.assertIn("Kanarieöarna", text)
        self.assertIn("ordkl='namn': 2", text)
        self.assertIn("Resolverad SAOL-UPOS för namn: PROPN=2", text)
        self.assertIn(capped, text)

    def test_no_false_limit_when_values_are_shorter(self) -> None:
        summary = build_summary([
            {"normaliserat_ord": "a", "ordkl": "s.", "upos": "NOUN"},
            {"normaliserat_ord": "b", "ordkl": "adj.", "upos": "ADJ"},
        ])
        self.assertEqual(4, summary["max_ordkl_length"])
        self.assertEqual(0, summary["ordkl_at_suspected_limit"])
        self.assertEqual([], summary["limit_value_groups"])


if __name__ == "__main__":
    unittest.main()
