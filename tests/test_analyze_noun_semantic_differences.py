from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_semantic_differences import (
    build_analysis,
    render_analysis,
)


class AnalyzeNounSemanticDifferencesTests(unittest.TestCase):
    def test_groups_semantic_rows_by_notation_and_change_type(self) -> None:
        rows = [
            {
                "record_id": "1",
                "lemma": "alarmklocka",
                "notation": "+n -klockor",
                "stycke": "a·larm|klocka",
                "status": "changed_forms",
                "added_forms": ["alarmklockor"],
                "semantic_removed_forms": ["alarmklocklockor"],
                "change_reasons": {"alarmklockor": "replace_tail"},
            },
            {
                "record_id": "2",
                "lemma": "alpklocka",
                "notation": "+n -klockor",
                "stycke": "alp|klocka",
                "status": "changed_forms",
                "added_forms": ["alpklockor"],
                "semantic_removed_forms": ["alpklocklockor"],
                "change_reasons": {"alpklockor": "replace_tail"},
            },
            {
                "record_id": "3",
                "lemma": "okänd",
                "notation": "okänd notation",
                "stycke": "okänd",
                "status": "unsupported",
                "semantic_removed_forms": [],
            },
        ]

        analysis = build_analysis(rows)
        self.assertEqual(2, analysis["semantic_rows"])
        self.assertEqual(1, analysis["notation_group_count"])
        self.assertEqual(2, analysis["notation_groups"][0]["count"])
        self.assertEqual("+n -klockor", analysis["notation_groups"][0]["key"])
        self.assertEqual(2, analysis["change_type_counts"]["replace_tail"])
        self.assertEqual("okänd notation", analysis["unsupported_groups"][0]["key"])

        text = render_analysis(analysis)
        self.assertIn("Semantiska poster: 2", text)
        self.assertIn("=== Grupp 1: 2 poster ===", text)
        self.assertIn("alarmklocka", text)
        self.assertIn("Unsupported grupperade efter notation", text)

    def test_ignores_noise_only_rows(self) -> None:
        analysis = build_analysis([
            {
                "lemma": "a-kassa",
                "notation": "+n a-kassor",
                "status": "changed_forms",
                "semantic_removed_forms": [],
                "legacy_noise_removed_forms": ["a"],
                "change_reasons": {},
            }
        ])
        self.assertEqual(0, analysis["semantic_rows"])
        self.assertEqual([], analysis["notation_groups"])


if __name__ == "__main__":
    unittest.main()
