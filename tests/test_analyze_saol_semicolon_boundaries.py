from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_semicolon_boundaries import (
    analyze_semicolon_boundaries,
    classify_predecessor,
    semicolon_predecessors,
)


class AnalyzeSaolSemicolonBoundariesTests(unittest.TestCase):
    def test_extracts_tokens_immediately_before_semicolons(self) -> None:
        self.assertEqual(
            ("+", "herrans"),
            semicolon_predecessors("best. +; i: vissa: uttryck: gen. herrans; pl. +ar"),
        )

    def test_classifies_boundary_tokens_structurally(self) -> None:
        cases = {
            "+": "unchanged",
            "+en": "append",
            "-ansökningar": "replace_tail",
            "herrans": "explicit",
            "används:": "comment_marker",
            "pl.": "label",
        }
        for token, expected in cases.items():
            with self.subTest(token=token):
                self.assertEqual(expected, classify_predecessor(token))

    def test_groups_examples_and_unclassified_boundaries(self) -> None:
        analysis = analyze_semicolon_boundaries(
            [
                {
                    "normaliserat_ord": "herr",
                    "text": "+n; i: vissa: uttryck: gen. herrans; pl. +ar",
                    "stycke": "herr",
                    "subnr": 1,
                },
                {
                    "normaliserat_ord": "obs",
                    "text": "ingen: böjning:; pl. saknas:",
                    "stycke": "obs",
                    "subnr": 2,
                },
            ]
        )
        self.assertEqual(2, analysis["records_with_semicolon"])
        self.assertEqual(3, analysis["semicolon_boundaries"])
        self.assertEqual(1, analysis["classification_counts"]["append"])
        self.assertEqual(1, analysis["classification_counts"]["explicit"])
        self.assertEqual(1, analysis["classification_counts"]["comment_marker"])


if __name__ == "__main__":
    unittest.main()
