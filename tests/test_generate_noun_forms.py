from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_noun_forms import (
    canonical_noun_row,
    generate_noun_artifact,
    render_comparison,
)


class GenerateNounFormsTests(unittest.TestCase):
    def test_ignores_non_nouns(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "glad",
            "upos": "ADJ",
            "text": "glatt glada",
        })
        self.assertIsNone(row)
        self.assertIsNone(comparison)

    def test_generates_regular_noun_with_provenance(self) -> None:
        row, comparison = canonical_noun_row({
            "normaliserat_ord": "bil",
            "upos": "NOUN",
            "text": "+en +ar",
            "homonr": "1",
            "subnr": 7,
            "stycke": "bil",
        })
        self.assertIsNotNone(row)
        assert row is not None
        written = {form["written_form"] for form in row["forms"]}
        self.assertIn("bil", written)
        self.assertIn("bilen", written)
        self.assertIn("bilar", written)
        self.assertTrue(all("source_stage" in form for form in row["forms"]))
        self.assertIsNotNone(comparison)

    def test_comparison_reports_completion_changes(self) -> None:
        rows, comparisons, summary = generate_noun_artifact([
            {
                "normaliserat_ord": "bil",
                "upos": "NOUN",
                "text": "+en +ar",
                "subnr": 1,
            }
        ])
        self.assertEqual(1, summary["noun_records"])
        self.assertEqual(1, len(rows))
        self.assertEqual(1, len(comparisons))
        text = render_comparison(summary, comparisons)
        self.assertIn("Substantivposter: 1", text)
        self.assertIn("Unika skrivna former:", text)

    def test_unsupported_noun_is_preserved_in_comparison(self) -> None:
        rows, comparisons, summary = generate_noun_artifact([
            {
                "normaliserat_ord": "testord",
                "upos": "NOUN",
                "text": "helt okänd notation 123",
                "subnr": 2,
            }
        ])
        self.assertEqual([], rows)
        self.assertEqual("unsupported", comparisons[0]["status"])
        self.assertEqual(1, summary["unsupported_noun_records"])


if __name__ == "__main__":
    unittest.main()
