from __future__ import annotations

import unittest

from swedish_wordlist_tools.filter_saol_review import remaining_rows


class FilterSaolReviewTests(unittest.TestCase):
    def test_removes_unique_matches(self) -> None:
        rows = [
            {"lemma": "abborrgrund", "saol_bar_reason": "unique_saol_bar_split"},
            {"lemma": "acidofilus", "saol_bar_reason": "no_saol_bar"},
        ]
        self.assertEqual(
            remaining_rows(rows),
            [{"lemma": "acidofilus", "saol_bar_reason": "no_saol_bar"}],
        )

    def test_keeps_mismatch_for_review(self) -> None:
        rows = [
            {"lemma": "himlabryn", "saol_bar_reason": "saol_bar_does_not_match_lemma"}
        ]
        self.assertEqual(remaining_rows(rows), rows)

    def test_removes_multiple_explicit_matches(self) -> None:
        rows = [
            {"lemma": "exempel", "saol_bar_reason": "multiple_saol_bar_splits"}
        ]
        self.assertEqual(remaining_rows(rows), [])


if __name__ == "__main__":
    unittest.main()
