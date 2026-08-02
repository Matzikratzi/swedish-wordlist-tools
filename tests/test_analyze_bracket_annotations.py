from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_bracket_annotations import (
    analyse_bracket_annotations,
    render_text,
)


class BracketAnnotationAnalysisTests(unittest.TestCase):
    def test_groups_annotations_and_full_notations(self) -> None:
        records = [
            {
                "normaliserat_ord": "reaktor",
                "homonr": "1",
                "text": "+n +er [-o>r-]",
            },
            {
                "normaliserat_ord": "radiator",
                "homonr": "1",
                "text": "+n +er [-o>r-]",
            },
            {
                "normaliserat_ord": "annan",
                "homonr": "2",
                "text": "+en [uttal]",
            },
            {"normaliserat_ord": "hus", "homonr": "1", "text": "+et"},
        ]

        summary = analyse_bracket_annotations(records)

        self.assertEqual(3, summary["records_with_brackets"])
        self.assertEqual(2, summary["unique_annotations"])
        self.assertEqual(2, summary["unique_notations"])
        self.assertEqual("[-o>r-]", summary["annotations"][0]["annotation"])
        self.assertEqual(2, summary["annotations"][0]["count"])
        self.assertEqual("+n +er [-o>r-]", summary["notations"][0]["notation"])
        self.assertEqual(2, summary["notations"][0]["count"])

    def test_reports_examples_in_text(self) -> None:
        summary = analyse_bracket_annotations(
            [{
                "normaliserat_ord": "reaktor",
                "homonr": "1",
                "text": "+n +er [-o>r-]",
            }]
        )

        text = render_text(summary)

        self.assertIn("[-o>r-] — 1 poster", text)
        self.assertIn("+n +er [-o>r-] — 1 poster", text)
        self.assertIn("reaktor (1)", text)


if __name__ == "__main__":
    unittest.main()
