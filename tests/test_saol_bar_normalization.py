from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_saol_bars import classify_candidate, compact_lemma, compact_word


class SaolBarNormalizationTests(unittest.TestCase):
    def test_ignores_markup_and_syllable_dots(self) -> None:
        marked = "<" + "sup" + ">1</" + "sup" + ">alko·hol"
        self.assertEqual(compact_word(marked), "alkohol")
        candidate = marked + "|be·ro·ende"
        reason, _ = classify_candidate("alkoholberoende", candidate)
        self.assertEqual(reason, "saol_bar_matches_lemma")

    def test_ignores_reflexive_sig(self) -> None:
        self.assertEqual(compact_lemma("anlagra sig"), "anlagra")
        reason, parts = classify_candidate("anlagra sig", "an|lagra")
        self.assertEqual(reason, "saol_bar_matches_lemma")
        self.assertEqual(parts, ["an", "lagra"])


if __name__ == "__main__":
    unittest.main()
