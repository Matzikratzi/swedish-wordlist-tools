from __future__ import annotations

import unittest

from swedish_wordlist_tools.recover_saol_bars import classify_candidate


class RecoverSaolBarsTests(unittest.TestCase):
    def test_accepts_accent_equivalent(self) -> None:
        reason, parts = classify_candidate("gruyereost", "gruyère|ost")
        self.assertEqual(reason, "saol_bar_matches_lemma")
        self.assertEqual(parts, ["gruyère", "ost"])

    def test_accepts_short_truncation(self) -> None:
        reason, parts = classify_candidate(
            "realisationsvinstbeskattning",
            "re·al·is·at·ions·vinst|be·skatt·nin",
        )
        self.assertEqual(reason, "saol_bar_matches_truncated_lemma")
        self.assertEqual(parts, ["re·al·is·at·ions·vinst", "be·skatt·nin"])

    def test_rejects_inflected_mismatch(self) -> None:
        reason, _parts = classify_candidate("himlabryn", "himla|bryn·et")
        self.assertEqual(reason, "saol_bar_does_not_match_lemma")

    def test_rejects_long_prefix_guess(self) -> None:
        reason, _parts = classify_candidate("socialbidragsberoendeextra", "socialbidrags|be·ro")
        self.assertEqual(reason, "saol_bar_does_not_match_lemma")


if __name__ == "__main__":
    unittest.main()
