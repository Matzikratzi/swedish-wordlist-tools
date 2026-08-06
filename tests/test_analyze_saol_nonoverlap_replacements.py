from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_nonoverlap_replacements import (
    analyze_nonoverlap_replacements,
    clean_stycke,
    replacement_tokens,
    split_compound,
)


class AnalyzeSaolNonoverlapReplacementsTests(unittest.TestCase):
    def test_cleans_and_splits_last_compound_head(self) -> None:
        self.assertEqual("stor|vägg|klocka", clean_stycke("stor|vägg|klocka"))
        self.assertEqual(("stor|vägg", "klocka"), split_compound("stor|vägg|klocka"))
        self.assertEqual(("bygel", "behå"), split_compound("bygel|be·hå"))

    def test_extracts_only_replacement_operations(self) -> None:
        self.assertEqual(
            ("-bh:n", "-bh:ar"),
            replacement_tokens("+n +ar _ -bh:n -bh:ar"),
        )

    def test_reports_nonoverlap_candidates_with_both_mechanical_forms(self) -> None:
        analysis = analyze_nonoverlap_replacements(
            [
                {
                    "normaliserat_ord": "bygelbehå",
                    "stycke": "bygel|be·hå",
                    "text": "+n +ar _ -bh:n -bh:ar",
                    "subnr": 1,
                },
                {
                    "normaliserat_ord": "gräsand",
                    "stycke": "gräs|and",
                    "text": "+en -änder",
                    "subnr": 2,
                },
            ]
        )
        self.assertEqual(2, analysis["nonoverlap_replacement_count"])
        self.assertEqual(
            ["bygelbh:ar", "bygelbh:n"],
            sorted(row["without_hyphen"] for row in analysis["rows"]),
        )
        self.assertEqual(
            ["bygel-bh:ar", "bygel-bh:n"],
            sorted(row["with_hyphen"] for row in analysis["rows"]),
        )
        self.assertNotIn("gräsand", {row["lemma"] for row in analysis["rows"]})


if __name__ == "__main__":
    unittest.main()
