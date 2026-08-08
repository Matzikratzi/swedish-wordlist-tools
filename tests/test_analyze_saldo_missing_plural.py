from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saldo_missing_plural import analyze_rows


class AnalyzeSaldoMissingPluralTests(unittest.TestCase):
    def test_selects_only_target_classification(self) -> None:
        rows = [
            {
                "lemma": "hund",
                "homonym_number": "1",
                "record_id": "1",
                "upos": "NOUN",
                "notation": "+en +ar",
                "coverage_status": "not_applicable",
                "mismatch_classification": "saldo_missing_plural",
                "extra_from_saol": ["hundar", "hundars", "hundarna", "hundarnas"],
                "missing_from_saol": [],
            },
            {
                "lemma": "katt",
                "mismatch_classification": "unclassified",
                "extra_from_saol": [],
                "missing_from_saol": [],
            },
        ]
        summary = analyze_rows(rows)
        self.assertEqual(1, summary["records"])
        self.assertEqual({"+en +ar": 1}, summary["notation_counts"])
        self.assertEqual({"NOUN": 1}, summary["upos_counts"])

    def test_groups_on_notation_and_relative_difference(self) -> None:
        rows = []
        for lemma in ("hund", "katt"):
            rows.append(
                {
                    "lemma": lemma,
                    "homonym_number": "1",
                    "record_id": lemma,
                    "upos": "NOUN",
                    "notation": "+en +ar",
                    "coverage_status": "not_applicable",
                    "mismatch_classification": "saldo_missing_plural",
                    "extra_from_saol": [
                        lemma + "ar",
                        lemma + "ars",
                        lemma + "arna",
                        lemma + "arnas",
                    ],
                    "missing_from_saol": [],
                }
            )
        summary = analyze_rows(rows)
        self.assertEqual(1, len(summary["groups"]))
        group = summary["groups"][0]
        self.assertEqual(2, group["count"])
        self.assertEqual(["+ar", "+arna", "+arnas", "+ars"], group["extra_pattern"])
        self.assertEqual([], group["missing_pattern"])

    def test_separates_same_notation_with_different_differences(self) -> None:
        rows = [
            {
                "lemma": "a",
                "upos": "NOUN",
                "notation": "+en +ar",
                "mismatch_classification": "saldo_missing_plural",
                "extra_from_saol": ["aar"],
                "missing_from_saol": [],
            },
            {
                "lemma": "b",
                "upos": "NOUN",
                "notation": "+en +ar",
                "mismatch_classification": "saldo_missing_plural",
                "extra_from_saol": ["ber"],
                "missing_from_saol": [],
            },
        ]
        summary = analyze_rows(rows)
        self.assertEqual(2, len(summary["groups"]))


if __name__ == "__main__":
    unittest.main()
