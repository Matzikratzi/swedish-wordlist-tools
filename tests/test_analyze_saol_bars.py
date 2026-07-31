from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_bars import (
    analyse_rows,
    build_saol_indexes,
    classify_candidate,
    extract_bar_candidates,
)


class AnalyzeSaolBarsTests(unittest.TestCase):
    def test_extracts_stycke(self) -> None:
        self.assertEqual(
            extract_bar_candidates({"stycke": "acajou|nöt"}),
            ["acajou|nöt"],
        )

    def test_candidate_reconstructs_lemma(self) -> None:
        reason, parts = classify_candidate("acajounöt", "acajou|nöt")
        self.assertEqual(reason, "saol_bar_matches_lemma")
        self.assertEqual(parts, ["acajou", "nöt"])

    def test_analyse_by_record_id(self) -> None:
        by_id, by_lemma = build_saol_indexes([
            {"id": "42", "normaliserat_ord": "acajounöt", "stycke": "acajou|nöt"}
        ])
        rows, counts = analyse_rows([
            {"lemma": "acajounöt", "record_id": "42", "analysis_reason": "no_candidate"}
        ], by_id, by_lemma)
        self.assertEqual(counts, {"unique_saol_bar_split": 1})
        self.assertEqual(rows[0]["saol_bar_splits"][0]["parts"], ["acajou", "nöt"])

    def test_falls_back_to_lemma(self) -> None:
        by_id, by_lemma = build_saol_indexes([
            {"normaliserat_ord": "ackordföljd", "stycke": "ackord|följd"}
        ])
        rows, counts = analyse_rows([
            {"lemma": "ackordföljd", "analysis_reason": "no_candidate"}
        ], by_id, by_lemma)
        self.assertEqual(counts, {"unique_saol_bar_split": 1})
        self.assertEqual(rows[0]["saol_bar_splits"][0]["parts"], ["ackord", "följd"])


if __name__ == "__main__":
    unittest.main()
