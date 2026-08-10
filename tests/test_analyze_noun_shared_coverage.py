from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_shared_coverage import branch_path, fallback_reason
from swedish_wordlist_tools.saol_notation import split_alternative_branches


class AnalyzeNounSharedCoverageTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_classifies_independent_shared_paths(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual("shared_labelled", branch_path(noun, self._tokens("pl. +ar")))
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("+en +ar")),
        )
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("brodern bröder")),
        )
        self.assertEqual("structural_uninflected", branch_path(noun, self._tokens("oböjl.")))

    def test_relative_and_explicit_atoms_can_mix_in_one_shared_sequence(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("+en bröder")),
        )
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("brodern +ar")),
        )

    def test_unknown_comment_syntax_stays_legacy_fallback(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual(
            "legacy_fallback",
            branch_path(noun, self._tokens("+en okändmarkör: +ar")),
        )

    def test_fallback_reason_separates_source_truncation_from_syntax(self) -> None:
        tokens = self._tokens("+en okändmarkör: +ar")
        self.assertEqual(
            "remaining_syntax",
            fallback_reason({"text": "+en okändmarkör: +ar"}, tokens),
        )
        self.assertEqual(
            "source_text_truncated",
            fallback_reason({"text": "x" * 50}, tokens),
        )


if __name__ == "__main__":
    unittest.main()
