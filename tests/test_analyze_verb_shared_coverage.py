from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_shared_coverage import analyze, classify_branch


class AnalyzeVerbSharedCoverageTests(unittest.TestCase):
    def test_classifies_basic_two_atom_sequences_as_shared(self) -> None:
        record = {"upos": "VERB", "text": "+de +t"}
        self.assertEqual("shared_basic_preterite_supine", classify_branch(record, "+de +t"))
        self.assertEqual(
            "shared_basic_preterite_supine",
            classify_branch({"upos": "VERB", "text": "andades andats"}, "andades andats"),
        )

    def test_classifies_present_and_participle_sequences_as_rich_shared(self) -> None:
        for text in (
            "-förde, -fört, pres. -för",
            "band, bundit, bunden bundet bundna, pres. binder",
            "djärvdes, pres. djärvs el. djärves",
            "pres. -fås, sup. -fåtts",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    "shared_rich_verb_slots",
                    classify_branch({"upos": "VERB", "text": text}, text),
                )

    def test_keeps_truncated_and_structural_uninflected_separate(self) -> None:
        self.assertEqual(
            "truncated_not_yet_shared",
            classify_branch({"upos": "VERB", "text": "x" * 50}, "gick, gått, pres."),
        )
        self.assertEqual(
            "structural_uninflected",
            classify_branch({"upos": "VERB", "text": "ingen: böjning:"}, "ingen: böjning:"),
        )

    def test_summary_counts_paths(self) -> None:
        records = [
            {"upos": "VERB", "normaliserat_ord": "a", "text": "+de +t", "ordkl": "v."},
            {"upos": "VERB", "normaliserat_ord": "b", "text": "gick, gått, pres. går", "ordkl": "v."},
            {"upos": "VERB", "normaliserat_ord": "c", "text": "ingen: böjning:", "ordkl": "v."},
        ]
        summary = analyze(records)
        self.assertEqual(3, summary["verb_records"])
        self.assertEqual(3, summary["branches"])
        self.assertEqual(2, summary["shared_branches"])
        self.assertEqual(66.67, summary["shared_branch_percent"])
        self.assertEqual(3, summary["clean_room_branches"])
        self.assertEqual(100.0, summary["clean_room_branch_percent"])


if __name__ == "__main__":
    unittest.main()
