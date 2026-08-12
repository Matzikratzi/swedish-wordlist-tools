from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_pronoun_notation import analyze, notation_signature


class AnalyzePronounNotationTests(unittest.TestCase):
    def test_signature_preserves_labels_alternatives_and_operations(self) -> None:
        self.assertEqual(
            (
                "LABEL:n.",
                "FORM",
                ";",
                "LABEL:gen.",
                "FORM",
                ";",
                "LABEL:pl.",
                "FORM",
                "ALT",
                "FORM",
            ),
            notation_signature("n. det; gen. dess; pl. de el. dom"),
        )

    def test_analyze_counts_pronouns_and_truncation(self) -> None:
        records = [
            {"upos": "PRON", "normaliserat_ord": "din", "text": "ditt dina"},
            {"upos": "PRON", "normaliserat_ord": "all", "text": "+t +a"},
            {"upos": "PRON", "normaliserat_ord": "den", "text": "x" * 49},
            {"upos": "PRON", "normaliserat_ord": "som", "text": None},
            {"upos": "NOUN", "normaliserat_ord": "bil", "text": "+en +ar"},
        ]
        report = analyze(records)
        self.assertEqual(4, report["pronoun_records"])
        self.assertEqual(3, report["with_text"])
        self.assertEqual(1, report["without_text"])
        self.assertEqual(1, report["truncated_records"])
        self.assertEqual(3, report["distinct_signatures"])


if __name__ == "__main__":
    unittest.main()
