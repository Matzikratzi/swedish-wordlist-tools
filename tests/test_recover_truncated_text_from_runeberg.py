from __future__ import annotations

import unittest

from swedish_wordlist_tools.recover_truncated_text_from_runeberg import (
    RunebergPage,
    compound_parts,
    match_row,
    truncated_candidates,
)


class RunebergTruncatedRecoveryTests(unittest.TestCase):
    def test_selects_only_exact_50_character_text(self) -> None:
        rows = [
            {"normaliserat_ord": "a", "upos": "NOUN", "text": "x" * 50},
            {"normaliserat_ord": "b", "upos": "NOUN", "text": "x" * 49},
            {"normaliserat_ord": "c", "upos": "ADJ", "text": "x" * 50},
        ]
        self.assertEqual(["a"], [row["normaliserat_ord"] for row in truncated_candidates(rows)])
        self.assertEqual(
            ["a", "c"],
            [row["normaliserat_ord"] for row in truncated_candidates(rows, upos=None)],
        )

    def test_extracts_compound_parts_from_stycke(self) -> None:
        self.assertEqual(
            ("auktions", "kammare"),
            compound_parts({"stycke": "auk·tions|kam·ma·re"}),
        )

    def test_prefers_exact_lemma_match(self) -> None:
        row = {
            "normaliserat_ord": "dasspapper",
            "stycke": "dass|papper",
            "text": "x" * 50,
        }
        pages = [RunebergPage(100, "Här står dasspapper med böjning.", "här står dasspapper med böjning")]
        result = match_row(row, pages)
        self.assertEqual("exact_lemma", result["status"])
        self.assertEqual("high", result["confidence"])
        self.assertEqual(100, result["runeberg_page"])

    def test_compound_family_is_secondary_evidence(self) -> None:
        row = {
            "normaliserat_ord": "auktionskammare",
            "stycke": "auktions|kammare",
            "text": "x" * 50,
        }
        text = "auktion -en -er s. auktions|bridge -bud -förrättare -kammare -utropare"
        pages = [RunebergPage(44, text, text.casefold())]
        result = match_row(row, pages)
        self.assertEqual("compound_family", result["status"])
        self.assertEqual("medium", result["confidence"])
        self.assertEqual(44, result["runeberg_page"])

    def test_no_evidence_stays_unresolved(self) -> None:
        row = {"normaliserat_ord": "saknas", "stycke": "sak|nas", "text": "x" * 50}
        result = match_row(row, [RunebergPage(1, "annat innehåll", "annat innehåll")])
        self.assertEqual("not_found", result["status"])
        self.assertEqual("none", result["confidence"])


if __name__ == "__main__":
    unittest.main()
