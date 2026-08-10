from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_unsupported_nouns import select, summarize


class AnalyzeUnsupportedNounsTests(unittest.TestCase):
    def test_selects_only_unsupported_nouns(self) -> None:
        rows = [
            {"upos": "NOUN", "status": "saol_pattern_unsupported", "lemma": "a"},
            {"upos": "NOUN", "status": "form_set_mismatch", "lemma": "b"},
            {"upos": "VERB", "status": "saol_pattern_unsupported", "lemma": "c"},
        ]
        self.assertEqual(["a"], [row["lemma"] for row in select(rows)])

    def test_excludes_truncated_unsupported_source_rows(self) -> None:
        notation = "+n [då>$en el. då>djen]; pl. +r [då>$er el. då>dje"
        self.assertEqual(50, len(notation))
        rows = [
            {"upos": "NOUN", "status": "saol_pattern_unsupported", "lemma": "doge", "notation": notation},
            {"upos": "NOUN", "status": "saol_pattern_unsupported", "lemma": "annan", "notation": "okänd"},
        ]
        self.assertEqual(["annan"], [row["lemma"] for row in select(rows)])

    def test_groups_by_exact_notation(self) -> None:
        rows = [
            {
                "upos": "NOUN",
                "status": "saol_pattern_unsupported",
                "lemma": "alpha",
                "homonym_number": "1",
                "notation": "x y",
                "ordkl": "s. x y",
                "generator": "canonical_artifact_missing",
            },
            {
                "upos": "NOUN",
                "status": "saol_pattern_unsupported",
                "lemma": "beta",
                "homonym_number": "2",
                "notation": "x y",
                "ordkl": "s. x y",
                "generator": "canonical_artifact_missing",
            },
            {
                "upos": "NOUN",
                "status": "saol_pattern_unsupported",
                "lemma": "gamma",
                "homonym_number": "1",
                "notation": "z",
                "ordkl": "s. z",
                "generator": "record_local_canonical",
            },
        ]
        summary = summarize(rows)
        self.assertEqual(3, summary["records"])
        self.assertEqual(2, summary["notations"])
        self.assertEqual("x y", summary["groups"][0]["notation"])
        self.assertEqual(2, summary["groups"][0]["count"])
        self.assertEqual(
            {"canonical_artifact_missing": 2},
            summary["groups"][0]["generators"],
        )


if __name__ == "__main__":
    unittest.main()
