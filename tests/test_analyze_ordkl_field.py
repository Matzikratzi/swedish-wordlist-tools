from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_ordkl_field import build_summary, render


class AnalyzeOrdklFieldTests(unittest.TestCase):
    def test_reports_length_limit_and_name_upos(self) -> None:
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
                "ordkl": "x" * 50,
                "upos": "X",
                "text": "(null)",
                "subnr": 3,
            },
        ]
        summary = build_summary(rows)
        self.assertEqual(50, summary["max_ordkl_length"])
        self.assertEqual(1, summary["ordkl_length_50"])
        self.assertEqual(2, summary["name_records"])
        self.assertEqual({"X": 1, "NOUN": 1}, summary["name_upos"])
        text = render(summary)
        self.assertIn("Kanarieöarna", text)
        self.assertIn("ordkl='namn': 2", text)

    def test_no_false_50_limit(self) -> None:
        summary = build_summary([
            {"normaliserat_ord": "a", "ordkl": "s.", "upos": "NOUN"},
            {"normaliserat_ord": "b", "ordkl": "adj.", "upos": "ADJ"},
        ])
        self.assertEqual(4, summary["max_ordkl_length"])
        self.assertEqual(0, summary["ordkl_length_50"])
        self.assertIn("Inga ordkl-värden är exakt 50", render(summary))


if __name__ == "__main__":
    unittest.main()
