from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_colon_markers import (
    analyze_colon_markers,
    colon_tokens,
    render_report,
)


class AnalyzeSaolColonMarkersTests(unittest.TestCase):
    def test_extracts_only_token_final_colons(self) -> None:
        self.assertEqual(
            ("i:", "används:", "i:", "uttryck:"),
            colon_tokens("+:n; i: pl. används: BB:t i: uttryck:"),
        )

    def test_strips_markup_without_creating_tokens(self) -> None:
        self.assertEqual(("i:",), colon_tokens("+<k>s</k>; i: pl. +"))

    def test_groups_case_insensitively_with_examples(self) -> None:
        analysis = analyze_colon_markers(
            [
                {
                    "normaliserat_ord": "ansökan",
                    "text": "best. +; i: pl. används: -ansökningar",
                    "stycke": "an|sök·an",
                    "subnr": 1,
                },
                {
                    "normaliserat_ord": "ante",
                    "text": "+de el. (I: ett: uttryck:) ante, +t",
                    "stycke": "ante",
                    "subnr": 2,
                },
            ]
        )
        self.assertEqual(2, analysis["records_with_colon_markers"])
        self.assertEqual(4, analysis["unique_colon_markers"])
        groups = {group["token"]: group for group in analysis["groups"]}
        self.assertEqual(2, groups["i:"]["count"])
        self.assertEqual({"ansökan", "ante"}, set(groups["i:"]["lemmas"]))
        report = render_report(analysis)
        self.assertIn("i: (2 förekomster", report)
        self.assertIn("ansökan", report)


if __name__ == "__main__":
    unittest.main()
