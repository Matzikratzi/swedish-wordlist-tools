from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from swedish_wordlist_tools.analyze_compounds import (
    analyse_rows,
    classify_splits,
    compact_word,
    find_compound_splits,
)


class AnalyzeCompoundsTests(unittest.TestCase):
    def test_compacts_separators_but_keeps_swedish_letters(self) -> None:
        self.assertEqual(compact_word("A-lagsmatch"), "alagsmatch")
        self.assertEqual(compact_word("räksmörgås"), "räksmörgås")

    def test_finds_unique_compound_split(self) -> None:
        splits = find_compound_splits(
            "fotbollsmatch",
            {"fotbolls", "fot"},
            {"match", "boll"},
        )
        self.assertEqual(splits, [("fotbolls", "match")])
        self.assertEqual(classify_splits(splits), "unique_compound_split")

    def test_reports_multiple_splits(self) -> None:
        splits = find_compound_splits(
            "solrosfrö",
            {"sol", "solros"},
            {"rosfrö", "frö"},
        )
        self.assertEqual(
            splits,
            [("sol", "rosfrö"), ("solros", "frö")],
        )
        self.assertEqual(classify_splits(splits), "multiple_compound_splits")

    def test_analyses_only_no_candidate_rows(self) -> None:
        rows, counts = analyse_rows(
            [
                {"lemma": "fotbollsmatch", "analysis_reason": "no_candidate"},
                {"lemma": "alskog", "analysis_reason": "single_edit_same_upos"},
                {"lemma": "okänd", "analysis_reason": "no_candidate"},
            ],
            {"fotbolls"},
            {"match"},
            {"fotbolls": {"fotboll"}, "match": {"match"}},
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            counts,
            {"no_compound_split": 1, "unique_compound_split": 1},
        )
        first = rows[0]
        self.assertEqual(first["compound_reason"], "unique_compound_split")
        self.assertEqual(first["compound_splits"][0]["left_analyses"], ["fotboll"])


if __name__ == "__main__":
    unittest.main()
