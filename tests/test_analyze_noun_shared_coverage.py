from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_shared_coverage import branch_path
from swedish_wordlist_tools.saol_notation import split_alternative_branches


class AnalyzeNounSharedCoverageTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_classifies_independent_shared_paths(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual("shared_labelled", branch_path(noun, self._tokens("pl. +ar")))
        self.assertEqual("shared_relative", branch_path(noun, self._tokens("+en +ar")))
        self.assertEqual("shared_explicit", branch_path(noun, self._tokens("brodern bröder")))
        self.assertEqual("structural_uninflected", branch_path(noun, self._tokens("oböjl.")))

    def test_unknown_mixed_syntax_stays_legacy_fallback(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual(
            "legacy_fallback",
            branch_path(noun, self._tokens("+en okändmarkör +ar")),
        )


if __name__ == "__main__":
    unittest.main()
