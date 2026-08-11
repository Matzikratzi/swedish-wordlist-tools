from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_notation_inventory import analyze


class AnalyzeVerbNotationInventoryTests(unittest.TestCase):
    def test_inventory_counts_only_verbs_and_describes_shapes(self) -> None:
        summary = analyze(
            [
                {"upos": "VERB", "normaliserat_ord": "testa", "text": "+r +de +t"},
                {"upos": "VERB", "normaliserat_ord": "göra", "text": "pres. gör; pret. gjorde"},
                {"upos": "NOUN", "normaliserat_ord": "test", "text": "+et +er"},
            ]
        )
        self.assertEqual(2, summary["verb_records"])
        self.assertEqual(0, summary["without_inflection_text"])
        self.assertEqual(2, summary["branches"])
        shapes = {group["shape"] for group in summary["top_shapes"]}
        self.assertIn("RELATIVE_ATOM RELATIVE_ATOM RELATIVE_ATOM", shapes)
        self.assertIn("SLOT_LABEL EXPLICIT_ATOM ; SLOT_LABEL EXPLICIT_ATOM", shapes)

    def test_inventory_counts_missing_and_truncated_sources(self) -> None:
        summary = analyze(
            [
                {"upos": "VERB", "normaliserat_ord": "x", "text": None},
                {"upos": "VERB", "normaliserat_ord": "y", "text": "x" * 50},
            ]
        )
        self.assertEqual(2, summary["verb_records"])
        self.assertEqual(1, summary["without_inflection_text"])
        self.assertEqual(1, summary["truncated_records"])


if __name__ == "__main__":
    unittest.main()
