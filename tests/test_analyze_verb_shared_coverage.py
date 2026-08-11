from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_shared_coverage import analyze, classify_branch


class AnalyzeVerbSharedCoverageTests(unittest.TestCase):
    def test_classifies_basic_two_atom_sequences_as_shared(self) -> None:
        record = {"upos": "VERB", "text": "+de +t"}
        self.assertEqual(
            "shared_basic_preterite_supine",
            classify_branch(record, "+de +t"),
        )
        self.assertEqual(
            "shared_basic_preterite_supine",
            classify_branch({"upos": "VERB", "text": "andades andats"}, "andades andats"),
        )

    def test_keeps_truncated_and_remaining_structure_separate(self) -> None:
        self.assertEqual(
            "truncated_not_yet_shared",
            classify_branch({"upos": "VERB", "text": "x" * 50}, "gick, gått, pres."),
        )
        self.assertEqual(
            "remaining_structure",
            classify_branch({"upos": "VERB", "text": "gick, gått, pres. går"}, "gick, gått, pres. går"),
        )

    def test_summary_counts_paths(self) -> None:
        records = [
            {"upos": "VERB", "normaliserat_ord": "a", "text": "+de +t", "ordkl": "v."},
            {"upos": "VERB", "normaliserat_ord": "b", "text": "gick, gått, pres. går", "ordkl": "v."},
        ]
        summary = analyze(records)
        self.assertEqual(2, summary["verb_records"])
        self.assertEqual(2, summary["branches"])
        self.assertEqual(1, summary["shared_branches"])
        self.assertEqual(50.0, summary["shared_branch_percent"])


if __name__ == "__main__":
    unittest.main()
