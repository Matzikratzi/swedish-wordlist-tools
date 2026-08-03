from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_mismatch_causes import (
    analyse_rows,
    classify_cause,
)


class AnalyzeNounMismatchCausesTests(unittest.TestCase):
    def test_classifies_zero_plural_against_regular_plural(self) -> None:
        row = {
            "lemma": "fiskelag",
            "notation": "+et; pl. +",
            "extra_from_saol": ["fiskelaget", "fiskelagets"],
            "missing_from_saol": [
                "fiskelagar", "fiskelagars", "fiskelagarna", "fiskelagarnas"
            ],
        }
        self.assertEqual("zero_plural_vs_regular_plural", classify_cause(row))

    def test_classifies_competing_plural_endings(self) -> None:
        row = {
            "lemma": "hajk",
            "notation": "+en +er",
            "extra_from_saol": ["hajker", "hajkers", "hajkerna", "hajkernas"],
            "missing_from_saol": ["hajkar", "hajkars", "hajkarna", "hajkarnas"],
        }
        self.assertEqual("competing_regular_plural_endings", classify_cause(row))

    def test_groups_only_remaining_noun_mismatches(self) -> None:
        rows = [
            {
                "lemma": "hajk",
                "upos": "NOUN",
                "status": "form_set_mismatch",
                "notation": "+en +er",
                "extra_from_saol": ["hajker", "hajkers", "hajkerna", "hajkernas"],
                "missing_from_saol": ["hajkar", "hajkars", "hajkarna", "hajkarnas"],
            },
            {
                "lemma": "springa",
                "upos": "VERB",
                "status": "form_set_mismatch",
                "extra_from_saol": [],
                "missing_from_saol": ["sprang"],
            },
        ]
        summary = analyse_rows(rows)
        self.assertEqual(1, summary["remaining_noun_mismatches"])
        self.assertEqual("competing_regular_plural_endings", summary["causes"][0]["cause"])


if __name__ == "__main__":
    unittest.main()
